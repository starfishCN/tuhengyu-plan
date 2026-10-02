"""图恒宇计划 —— 拟人化生活插件

给 bot「完整的一生」：它有自己的作息，会自己发空间。

第一版范围：作息 + 调度器 + 发空间。
    调度器按「活跃时段 + 检查间隔 + 触发概率」决定何时行动；
    每次行动时先用 AstrBot 的模型生成内容，再发到 QQ 空间。

适配 AstrBot v4（API 依据：/AstrBot/astrbot/core/star/ 源码，2026-10-01 核对）。
    - 插件类继承 star.Star，元信息写在 metadata.yaml（@register 装饰器已废弃）
    - 实例方法 async def initialize(self) / async def terminate(self)
    - 平台访问：context.get_platform("aiocqhttp") → platform.get_client() → bot.call_action()
"""
import asyncio
import random
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Image, Poke
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request as web_request

from .core.classify import classify_image
from .core.favour import FavourStore, build_injection, parse_state_marker
from .core.intent import FALLBACK as INTENT_FALLBACK
from .core.intent import labels as intent_labels
from .core.persona import resolve_persona
from .core.proactive import build_proactive_prompt, decide_proactive
from .core.poke import IGNORE as POKE_IGNORE
from .core.poke import build_poke_prompt, decide as decide_poke, fallback_text
from .core.scheduler import LifeScheduler
from .core.stickers import SYSTEM_LABELS, read_base64, save_collected, thumb_b64

# Web API 路由必须以插件名为前缀（AstrBot 约定，2026-10-01 核对官方文档）。
PLUGIN_NAME = "astrbot_plugin_tuhengyu"


class TuhengyuPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.config = config or {}
        self._scheduler = None
        self._task = None
        self._favour_store = None
        self._poke_log = {}  # 戳一戳：键 → [时间戳]，用于连戳计数与冷却
        self._bridge_obj = None  # OneBot 桥（回戳用 send_poke 动作）
        self._tok_last = None  # 最近一次 LLM 请求的构成快照（token 诊断用）
        self._tok_stats = self._tok_load()  # 今日请求 / token 累计（存盘）
        self._groups = {}  # 群聊观察：gid → {msgs, last_spoke, day, count}
        self._proactive_load()  # 读回每群的冷却 / 今日计数
        # 注册插件页面的后端 API（页面在 pages/status/）。
        try:
            context.register_web_api(
                f"/{PLUGIN_NAME}/status",
                self.page_status,
                ["GET"],
                "插件页面：运行状态",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/reschedule",
                self.page_reschedule,
                ["POST"],
                "插件页面：重算作息",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/test-moment",
                self.page_test_moment,
                ["POST"],
                "插件页面：立即发一条空间动态",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-reload",
                self.page_sticker_reload,
                ["POST"],
                "插件页面：重扫表情包目录",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/stickers",
                self.page_stickers,
                ["GET"],
                "插件页面：表情包库（按意图分组）",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-category",
                self.page_sticker_category,
                ["POST"],
                "插件页面：新建表情包分类",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-upload",
                self.page_sticker_upload,
                ["POST"],
                "插件页面：上传表情包",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-classify",
                self.page_sticker_classify,
                ["POST"],
                "插件页面：识图自动归类",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/settings",
                self.page_settings_get,
                ["GET"],
                "插件页面：读取设置",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/settings",
                self.page_settings_post,
                ["POST"],
                "插件页面：保存设置",
            )
        except Exception as e:  # 注册失败不影响主体功能
            self.logger.warning(f"[图恒宇] 注册页面 API 失败：{e}")

    # ---------- 生命周期 ----------
    async def initialize(self):
        """插件加载后调用：启动生活调度器。"""
        if not self.config.get("enabled", True):
            self.logger.info("[图恒宇] 插件已禁用，不启动调度器。")
            return
        self._scheduler = LifeScheduler(self.context, self.config, self._data_dir())
        await self._refresh_persona()  # 先解析人设，作息生成依赖它
        await self._scheduler.setup()  # 生成 / 读取作息（失败会兜底，不抛）
        self._scheduler.add_action(self._maybe_proactive)  # 主动插话挂到调度器
        self._task = asyncio.create_task(self._scheduler.run(), name="tuhengyu_scheduler")
        self.logger.info("[图恒宇] 生活调度器已启动。")

    async def _refresh_persona(self) -> None:
        """重新从 AstrBot 解析当前人设并下发给调度器 / 作息。

        每次对外查询前都跑一遍：这样博士在 AstrBot 里换了人格，插件立刻跟上，
        不必重启插件、也不必再往插件里抄一份人设。
        """
        if self._scheduler is None:
            return
        try:
            text, label, name = await resolve_persona(self.context, self.config)
        except Exception as e:  # 解析失败不致命，退回原值
            self.logger.warning(f"[图恒宇] 解析人设失败：{e}")
            return
        self._scheduler.set_persona(text, label, name)

    def _data_dir(self) -> str:
        """插件数据目录：data/plugin_data/astrbot_plugin_tuhengyu。"""
        import os

        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

            return os.path.join(get_astrbot_plugin_data_path(), "astrbot_plugin_tuhengyu")
        except Exception as e:  # API 变动时不致命，退到插件目录旁
            self.logger.warning(f"[图恒宇] 取数据目录失败，退回插件目录：{e}")
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    async def terminate(self):
        """插件卸载时调用：停调度器。"""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.logger.info("[图恒宇] 生活调度器已停止。")

    # ---------- 回复附带表情包 ----------
    @filter.on_decorating_result()
    async def attach_sticker(self, event: AstrMessageEvent):
        """bot 每次回复发出前，按概率在消息末尾附一张表情包。

        被动附带，不主动发消息；库为空时什么都不做。
        选图见 core/stickers.py：按「此刻状态 + 本条回复正文」里的标签名挑。
        """
        if self._scheduler is None:
            return
        sec = self.config.get("sticker") if isinstance(self.config, dict) else None
        sec = sec if isinstance(sec, dict) else {}
        if not sec.get("enabled", True):
            return
        if sec.get("send_separate", False):
            return  # 单独发模式：这里不附，交给 after_message_sent 另发一条
        try:
            prob = float(sec.get("probability", 0.35))
        except (TypeError, ValueError):
            prob = 0.35
        if prob <= 0 or random.random() > prob:
            return
        result = event.get_result()
        if result is None or not getattr(result, "chain", None):
            return
        try:
            reply_text = result.get_plain_text()
        except Exception:
            reply_text = ""
        st = self._scheduler.schedule.state_at()
        path = self._scheduler.pick_sticker(f"{reply_text}{st.scene}{st.state}")
        if path is None:
            return
        b64 = read_base64(path)
        if not b64:
            return
        from astrbot.api.message_components import Image

        result.chain.append(Image.fromBase64(b64))

    # ---------- 回复后单独发一条表情包 ----------
    @filter.after_message_sent()
    async def send_sticker_separately(self, event: AstrMessageEvent):
        """单独发模式：bot 回复发出后，按概率再发一条只含表情包的消息。

        与 attach_sticker 互斥（靠 sticker.send_separate 分流）：关时这里是空的。
        选图与概率同 attach_sticker，保持两条路径口径一致。
        """
        if self._scheduler is None:
            return
        sec = self.config.get("sticker") if isinstance(self.config, dict) else None
        sec = sec if isinstance(sec, dict) else {}
        if not sec.get("enabled", True):
            return
        if not sec.get("send_separate", False):
            return
        try:
            prob = float(sec.get("probability", 0.35))
        except (TypeError, ValueError):
            prob = 0.35
        if prob <= 0 or random.random() > prob:
            return
        try:
            reply_text = event.get_result().get_plain_text()
        except Exception:
            reply_text = ""
        st = self._scheduler.schedule.state_at()
        path = self._scheduler.pick_sticker(f"{reply_text}{st.scene}{st.state}")
        if path is None:
            return
        b64 = read_base64(path)
        if not b64:
            return
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Image

        try:
            await event.send(MessageChain([Image.fromBase64(b64)]))
        except Exception as e:  # 发送失败不影响主回复
            self.logger.warning(f"[图恒宇] 单独发表情包失败：{e}")

    # ---------- 对话中自动收集表情包 ----------
    @filter.event_message_type(EventMessageType.ALL)
    async def collect_sticker(self, event: AstrMessageEvent):
        """把对话里收到的图片存进表情包库（bot 自己攒表情包）。

        只存图，不改消息、不回复。同内容按 md5 去重。
        """
        if self._scheduler is None:
            return
        sec = self.config.get("sticker") if isinstance(self.config, dict) else None
        sec = sec if isinstance(sec, dict) else {}
        if not sec.get("collect_enabled", True):
            return
        try:
            msgs = event.get_messages()
        except Exception:
            return
        imgs = [m for m in msgs if isinstance(m, Image)]
        if not imgs:
            return

        import os

        label = str(sec.get("collect_label", "collected") or "collected").strip() or "collected"
        root = os.path.join(self._data_dir(), "stickers")
        saved = 0
        for img in imgs[:2]:  # 单条消息最多收两张，避免刷屏
            try:
                path = await img.convert_to_file_path()
            except Exception as e:  # 下载/解析失败不影响消息流程
                self.logger.debug(f"[图恒宇] 取图失败：{e}")
                continue
            if save_collected(root, path, label):
                saved += 1
        if saved:
            self._scheduler.stickers.reload()
            self.logger.info(f"[图恒宇] 对话中收集到 {saved} 张表情包 → {label}/")

    # ---------- 好感度：注入 + 回收 ----------
    def _favour_cfg(self) -> dict:
        sec = self.config.get("favour") if isinstance(self.config, dict) else None
        return sec if isinstance(sec, dict) else {}

    def _favour(self) -> FavourStore:
        if self._favour_store is None:
            self._favour_store = FavourStore(self._data_dir())
        return self._favour_store

    def _scope(self, event: AstrMessageEvent, sec: dict) -> str | None:
        """会话独立开关；关着返回 None（全局状态）。"""
        if not sec.get("session_based", False):
            return None
        try:
            return str(event.unified_msg_origin or "") or None
        except Exception:
            return None

    @filter.on_llm_request()
    async def inject_favour(self, event: AstrMessageEvent, req: ProviderRequest):
        """把当前三维状态与更新指令追加到 system prompt。"""
        self._tok_snapshot(event, req)
        sec = self._favour_cfg()
        if not sec.get("enabled", True) or not sec.get("inject", True):
            return
        try:
            uid = str(event.get_sender_id() or "")
            if not uid:
                return
            state = self._favour().get(uid, self._scope(event, sec))
            req.system_prompt = (req.system_prompt or "") + build_injection(state)
        except Exception as e:
            self.logger.warning(f"[图恒宇] 注入好感度失败：{e}")

    @filter.on_llm_response()
    async def collect_favour(self, event: AstrMessageEvent, resp: LLMResponse):
        """从回复里把状态行整行剥离并落库。缺字段保持原值，不猜。"""
        self._tok_output(resp)
        sec = self._favour_cfg()
        if not sec.get("enabled", True):
            return
        try:
            text = resp.completion_text or ""
            cleaned, patch = parse_state_marker(text)
            if patch is None:
                return
            if cleaned != text:
                resp.completion_text = cleaned
            uid = str(event.get_sender_id() or "")
            if uid:
                self._favour().update(uid, patch, self._scope(event, sec))
        except Exception as e:
            self.logger.warning(f"[图恒宇] 回收好感度失败：{e}")

    # ---------- 戳一戳 ----------
    def _poke_cfg(self) -> dict:
        sec = self.config.get("poke") if isinstance(self.config, dict) else None
        return sec if isinstance(sec, dict) else {}

    def _bridge(self):
        """取 OneBot 桥（懒加载并缓存）。"""
        if self._bridge_obj is None:
            try:
                from .core.onebot import OneBotBridge

                self._bridge_obj = OneBotBridge(self.context)
            except Exception as e:
                self.logger.warning(f"[图恒宇] 初始化 OneBot 桥失败：{e}")
                return None
        return self._bridge_obj

    async def _send_poke(self, uid: str, group: bool, group_id: str = "") -> bool:
        """经协议端动作回戳一下。

        注意：不走 poke 消息段。现行协议端（SnowLuma）的 poke 段仅允许私聊、
        且必须是唯一段，群聊直接判 UNSENDABLE_TYPE 拒收；正解是 send_poke 动作，
        user_id 必填，群聊另带 group_id，由协议端自行路由群/私聊。
        """
        bridge = self._bridge()
        if bridge is None:
            return False
        params = {"user_id": uid}
        if group and group_id:
            params["group_id"] = group_id
        return await bridge.call_ok("send_poke", **params)

    def _poke_touch(self, key: str, now: float, window: float, cooldown: float) -> tuple[int, bool]:
        """记一次戳，返回 (含本次的窗口内次数, 是否在冷却中)。"""
        prev = [t for t in self._poke_log.get(key, []) if now - t <= max(window, cooldown)]
        cooling = bool(prev) and (now - prev[-1]) < cooldown
        prev.append(now)
        self._poke_log[key] = prev
        return len(prev), cooling

    async def _poke_text(self, event, reaction, state: dict, scene: str, st_state: str, group: bool) -> str:
        """让模型按人设回一句。拿不到模型返回空串（调用方回落台词池）。"""
        try:
            persona, _label, _name = await resolve_persona(self.context, self.config)
        except Exception:
            persona = ""
        persona = persona or str(self.config.get("persona_prompt", "") or "")
        if not persona:
            self.logger.info("[图恒宇] 戳一戳：无人设可用，回落台词池。")
            return ""
        psec = self._poke_cfg()
        prompt = build_poke_prompt(
            kind=reaction.kind,
            favour=int(state.get("favour", 0) or 0),
            relationship=str(state.get("relationship", "")),
            attitude=str(state.get("attitude", "")),
            scene=scene,
            state=st_state,
            group=group,
            persona=persona,
        )
        provider = self._pick_provider(psec)
        if provider is None:
            self.logger.info("[图恒宇] 戳一戳：无可用模型，回落台词池。")
            return ""
        try:
            resp = await provider.text_chat(prompt=prompt)
            text = (getattr(resp, "completion_text", "") or "").strip().strip('"').strip()
            return text[:60]
        except Exception as e:
            self.logger.warning(f"[图恒宇] 生成戳一戳回应失败：{e}")
            return ""

    def _pick_provider(self, sec: dict):
        """取一个对话模型实例：优先配置里指定的 id，否则 AstrBot 当前默认。"""
        pid = str(sec.get("model", "") or "").strip()
        if pid:
            try:
                prov = self.context.get_provider_by_id(pid)
                if prov is not None:
                    return prov
            except Exception as e:
                self.logger.warning(f"[图恒宇] 取指定模型 {pid} 失败：{e}")
        try:
            return self.context.get_using_provider()
        except Exception as e:
            self.logger.warning(f"[图恒宇] 取默认模型失败：{e}")
        return None

    @filter.event_message_type(EventMessageType.ALL)
    async def on_poke(self, event: AstrMessageEvent):
        """被戳一下：回戳 / 说一句 / 无视，按人设 + 好感 + 状态 + 频次决定。

        只处理带 Poke 组件的事件，其余消息一律不碰。
        """
        sec = self._poke_cfg()
        if not sec.get("enabled", True):
            return
        try:
            msgs = event.get_messages()
        except Exception:
            return
        if not any(isinstance(m, Poke) for m in msgs):
            return
        # 是戳事件：默认 LLM 链路要掐掉（私聊会无条件唤醒它）。
        try:
            event.should_call_llm(True)
        except Exception:
            pass

        import time as _time

        now = _time.time()
        uid = str(event.get_sender_id() or "")
        if not uid:
            return
        try:
            umo = str(event.unified_msg_origin or "")
        except Exception:
            umo = ""
        try:
            group = not event.is_private_chat()
        except Exception:
            group = False
        try:
            group_id = str(event.get_group_id() or "")
        except Exception:
            group_id = ""

        def _int(key: str, default: int) -> int:
            try:
                return int(sec.get(key, default))
            except (TypeError, ValueError):
                return default

        cooldown = _int("cooldown_seconds", 30)
        window = _int("repeat_window_seconds", 60)
        threshold = _int("snap_threshold", 3)
        try:
            prob = float(sec.get("poke_back_prob", 0.6))
        except (TypeError, ValueError):
            prob = 0.6
        try:
            speak_prob = float(sec.get("speak_prob", 0.75))
        except (TypeError, ValueError):
            speak_prob = 0.75

        repeat, cooling = self._poke_touch(f"{umo}:{uid}", now, window, cooldown)

        fsec = self._favour_cfg()
        if fsec.get("enabled", True):
            state = self._favour().get(uid, self._scope(event, fsec))
        else:
            state = {"favour": 0, "attitude": "中立", "relationship": "陌生人"}
        favour = int(state.get("favour", 0) or 0)

        awake, scene, st_state = True, "", ""
        if self._scheduler is not None:
            try:
                st = self._scheduler.schedule.state_at()
                awake = bool(st.awake)
                scene = st.scene or ""
                st_state = st.state or ""
            except Exception:
                pass

        reaction = decide_poke(
            favour=favour,
            awake=awake,
            repeat=repeat,
            cooling=cooling,
            poke_back_prob=prob,
            speak_prob=speak_prob,
            snap_threshold=threshold,
        )
        if reaction.kind == POKE_IGNORE:
            if reaction.reason != "冷却中":
                self.logger.info(f"[图恒宇] 戳一戳：这次不搭理（{reaction.reason}）。")
            return

        if reaction.poke_back():
            if not await self._send_poke(uid, group, group_id):
                self.logger.warning("[图恒宇] 回戳失败：协议端未接受 send_poke 动作。")

        if not reaction.speak():
            return
        text = ""
        if sec.get("use_model", True):
            text = await self._poke_text(event, reaction, state, scene, st_state, group)
        if not text:
            text = fallback_text(reaction, favour=favour, awake=awake, group=group)
        if text:
            yield event.plain_result(text)

    # ---------- 群聊主动插话 ----------
    def _proactive_cfg(self) -> dict:
        sec = self.config.get("proactive") if isinstance(self.config, dict) else None
        return sec if isinstance(sec, dict) else {}

    def _proactive_path(self) -> str:
        import os

        return os.path.join(self._data_dir(), "proactive.json")

    def _proactive_load(self) -> None:
        """读回每群的冷却 / 今日计数（群聊内容本身不落盘）。"""
        import json
        import os

        self._groups = {}
        try:
            if not os.path.exists(self._proactive_path()):
                return
            with open(self._proactive_path(), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for gid, d in data.items():
                    d = d if isinstance(d, dict) else {}
                    self._groups[str(gid)] = {
                        "msgs": [],
                        "last_spoke": float(d.get("last_spoke") or 0),
                        "day": str(d.get("day") or ""),
                        "count": int(d.get("count") or 0),
                    }
        except Exception as e:
            self.logger.debug(f"[图恒宇] 读主动发言状态失败：{e}")

    def _proactive_save(self) -> None:
        import json

        try:
            data = {
                gid: {
                    "last_spoke": g.get("last_spoke", 0),
                    "day": g.get("day", ""),
                    "count": g.get("count", 0),
                }
                for gid, g in self._groups.items()
            }
            with open(self._proactive_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            self.logger.debug(f"[图恒宇] 写主动发言状态失败：{e}")

    @filter.event_message_type(EventMessageType.ALL)
    async def watch_group(self, event: AstrMessageEvent):
        """记住群里最近说了什么，供主动插话接话用。只记群聊、只记文字。

        记录常开：`enabled` 只控制「自动插话」这个行为，不控制观察。
        否则刚把开关打开的瞬间手里一条上下文都没有，谁也接不上。
        """
        try:
            if event.is_private_chat():
                return
        except Exception:
            return
        try:
            gid = str(event.get_group_id() or "")
        except Exception:
            gid = ""
        if not gid:
            return
        try:
            text = str(event.message_str or "").strip()
        except Exception:
            text = ""
        if not text:
            return
        import time as _time

        now = _time.time()
        try:
            sender = str(event.get_sender_name() or "") or str(event.get_sender_id() or "")
        except Exception:
            sender = ""
        g = self._groups.setdefault(
            gid, {"msgs": [], "last_spoke": 0.0, "day": "", "count": 0}
        )
        msgs = g["msgs"]
        msgs.append([now, sender, text[:60]])
        del msgs[:-20]  # 只留最近 20 条
        cutoff = now - 1800  # 半小时前的丢掉，别拿旧话题硬接
        while msgs and msgs[0][0] < cutoff:
            msgs.pop(0)

    async def _proactive_text(self, recent: list, st, max_chars: int, sec: dict) -> str:
        """让模型按人设接一句。拿不到模型返回空串。"""
        try:
            persona, _label, _name = await resolve_persona(self.context, self.config)
        except Exception:
            persona = ""
        persona = persona or str(self.config.get("persona_prompt", "") or "")
        lines = [f"{m[1]}：{m[2]}" for m in recent][-10:]
        prompt = build_proactive_prompt(
            persona=persona,
            lines=lines,
            scene=getattr(st, "scene", "") or "",
            state=getattr(st, "state", "") or "",
            max_chars=max_chars,
        )
        provider = self._pick_provider(sec)
        if provider is None:
            self.logger.info("[图恒宇] 主动插话：无可用模型。")
            return ""
        try:
            resp = await provider.text_chat(prompt=prompt)
            text = (getattr(resp, "completion_text", "") or "").strip().strip('"').strip()
        except Exception as e:
            self.logger.warning(f"[图恒宇] 生成插话失败：{e}")
            return ""
        if text in ("-", "—", "－", "无", "（无）"):
            return ""
        return text[:60]

    async def _maybe_proactive(self, now, st) -> None:
        """醒着时，偶尔在群里接一句。挂给调度器，每个 tick 跑一次。"""
        sec = self._proactive_cfg()
        if not sec.get("enabled", False):
            return
        if not getattr(st, "awake", True):
            return
        bridge = self._bridge()
        if bridge is None:
            return
        import time as _time

        now_ts = _time.time()
        today = datetime.now().strftime("%Y-%m-%d")

        def _num(key, default, cast):
            try:
                return cast(sec.get(key, default))
            except (TypeError, ValueError):
                return default

        prob = _num("probability", 0.05, float)
        cooldown = _num("cooldown_minutes", 30, float) * 60
        daily_cap = _num("daily_cap_per_group", 8, int)
        min_recent = _num("min_recent_messages", 3, int)
        hot = _num("hot_window_minutes", 10, float) * 60
        max_chars = _num("max_chars", 20, int)
        whitelist = [
            g.strip()
            for g in str(sec.get("groups", "") or "").replace("，", ",").split(",")
            if g.strip()
        ]

        for gid, g in list(self._groups.items()):
            if not g.get("msgs"):
                continue
            if whitelist and gid not in whitelist:
                continue
            recent = [m for m in g["msgs"] if now_ts - m[0] <= hot]
            if len(recent) < min_recent:
                continue
            d = decide_proactive(
                awake=True,
                cooling=(now_ts - float(g.get("last_spoke") or 0)) < cooldown,
                daily_count=int(g.get("count") or 0) if g.get("day") == today else 0,
                daily_cap=daily_cap,
                recent_count=len(recent),
                min_recent=min_recent,
                prob=prob,
            )
            if not d.act:
                continue
            reply = await self._proactive_text(recent, st, max_chars, sec)
            if not reply:
                continue
            ok = False
            try:
                ok = await bridge.call_ok("send_group_msg", group_id=int(gid), message=reply)
            except Exception as e:
                self.logger.warning(f"[图恒宇] 主动插话发送异常：{e}")
            if ok:
                g["last_spoke"] = now_ts
                if g.get("day") != today:
                    g["day"] = today
                    g["count"] = 0
                g["count"] = int(g.get("count") or 0) + 1
                self._proactive_save()
                self.logger.info(f"[图恒宇] 主动插话（群 {gid}）：{reply[:30]}")
            else:
                self.logger.warning("[图恒宇] 主动插话发送失败。")
            return  # 一次循环最多发一句

    @filter.command("图恒宇插话")
    async def test_proactive(self, event: AstrMessageEvent):
        """管理员私聊指令：/图恒宇插话 群号 —— 让它在指定群接一句。

        走管理员私聊通道：群里不响应，回执也只落在私聊，
        免得把运维动作暴露在群里。忽略概率、冷却与每日上限，只用于验证链路。
        """
        try:
            if not event.is_private_chat():
                return  # 群里不响应
        except Exception:
            pass
        try:
            is_admin = bool(event.is_admin())
        except Exception:
            is_admin = False
        if not is_admin:
            yield event.plain_result("[图恒宇] 该指令仅管理员可用。")
            return

        import re

        raw = str(event.message_str or "").strip()
        gids = re.findall(r"\d{5,}", raw)
        sec = self._proactive_cfg()
        if not gids:
            known = [g for g, d in self._groups.items() if d.get("msgs")]
            tip = (
                "[图恒宇] 用法：/图恒宇插话 群号\n"
                f"已知群：{'、'.join(known) if known else '（还没记到任何群，先在群里聊两句）'}"
            )
            yield event.plain_result(tip)
            return

        gid = gids[0]
        g = self._groups.get(gid)
        if not g or not g.get("msgs"):
            yield event.plain_result(f"[图恒宇] 群 {gid} 还没记录到聊天，先在群里聊两句再试。")
            return
        st = self._scheduler.schedule.state_at() if self._scheduler else None
        try:
            max_chars = int(sec.get("max_chars", 20))
        except (TypeError, ValueError):
            max_chars = 20
        recent = g["msgs"][-10:]
        seen = "\n".join(f"{i + 1}. {mm[1]}：{mm[2]}" for i, mm in enumerate(recent[-5:]))
        reply = await self._proactive_text(recent, st, max_chars, sec)
        if not reply:
            yield event.plain_result("[图恒宇] 没生成出能接的一句。\n它看到的最近几条：\n" + seen)
            return
        bridge = self._bridge()
        ok = False
        if bridge is not None:
            try:
                ok = await bridge.call_ok("send_group_msg", group_id=int(gid), message=reply)
            except Exception as e:
                self.logger.warning(f"[图恒宇] 测试插话发送异常：{e}")
        head = f"[图恒宇] 已发送到群 {gid}：{reply}" if ok else "[图恒宇] 发送失败，看日志。"
        yield event.plain_result(head + "\n它看到的最近几条：\n" + seen)

    # ---------- token 诊断 ----------
    # 折算口径：中文 1 token ≈ 2.06 字符（实测 7994 字符 ≈ 3876 token）。
    _TOKEN_CHARS = 2.06

    def _est_tokens(self, chars) -> int:
        try:
            return int(round(int(chars or 0) / self._TOKEN_CHARS))
        except Exception:
            return 0

    def _tok_path(self) -> str:
        import os

        return os.path.join(self._data_dir(), "token_stats.json")

    def _tok_blank(self) -> dict:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "reqs": 0,
            "in": 0,
            "out": 0,
            "p_reqs": 0,
            "p_in": 0,
        }

    def _tok_load(self) -> dict:
        import json
        import os

        blank = self._tok_blank()
        try:
            if os.path.exists(self._tok_path()):
                with open(self._tok_path(), encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("date") == blank["date"]:
                    for k, v in blank.items():
                        data.setdefault(k, v)
                    return data
        except Exception as e:
            self.logger.debug(f"[图恒宇] 读 token 统计失败：{e}")
        return blank

    def _tok_roll(self) -> None:
        if self._tok_stats.get("date") != datetime.now().strftime("%Y-%m-%d"):
            self._tok_stats = self._tok_blank()

    def _tok_save(self) -> None:
        import json

        try:
            with open(self._tok_path(), "w", encoding="utf-8") as f:
                json.dump(self._tok_stats, f, ensure_ascii=False)
        except Exception as e:
            self.logger.debug(f"[图恒宇] 写 token 统计失败：{e}")

    def _tok_snapshot(self, event, req) -> None:
        """记下一次 LLM 请求的构成，并累计今日用量。只在 on_llm_request 里跑。"""
        try:
            sys_text = getattr(req, "system_prompt", "") or ""
            ctxs = getattr(req, "contexts", None) or []
            ctx_chars = 0
            for m in ctxs:
                if not isinstance(m, dict):
                    continue
                c = m.get("content")
                if isinstance(c, str):
                    ctx_chars += len(c)
                elif isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            ctx_chars += len(part["text"])
            tools = []
            ts = getattr(req, "func_tool", None)
            for t in (getattr(ts, "tools", None) or []):
                name = getattr(t, "name", "") or "?"
                desc = getattr(t, "description", "") or ""
                try:
                    import json as _json

                    params = _json.dumps(getattr(t, "parameters", None) or {}, ensure_ascii=False)
                except Exception:
                    params = ""
                tools.append((name, len(desc) + len(params)))
            tools.sort(key=lambda x: -x[1])
            prompt_chars = len(getattr(req, "prompt", "") or "")
            self._tok_last = {
                "at": datetime.now().strftime("%H:%M:%S"),
                "model": str(getattr(req, "model", "") or "") or "(默认)",
                "sys_chars": len(sys_text),
                "ctx_count": len(ctxs),
                "ctx_chars": ctx_chars,
                "tools": tools,
                "tools_chars": sum(c for _n, c in tools),
                "prompt_chars": prompt_chars,
            }
            self._tok_roll()
            is_private = False
            try:
                is_private = bool(event.is_private_chat())
            except Exception:
                pass
            total = self._est_tokens(len(sys_text) + ctx_chars + prompt_chars)
            self._tok_stats["reqs"] += 1
            self._tok_stats["in"] += total
            if is_private:
                self._tok_stats["p_reqs"] += 1
                self._tok_stats["p_in"] += total
            self._tok_save()
        except Exception as e:
            self.logger.debug(f"[图恒宇] token 快照失败：{e}")

    def _tok_output(self, resp) -> None:
        """累计一次输出的 token：有 usage 用真值，否则按回复字符估。"""
        try:
            self._tok_roll()
            out = 0
            usage = getattr(resp, "usage", None)
            if usage is not None:
                try:
                    out = int(getattr(usage, "output", 0) or 0)
                except Exception:
                    out = 0
            if not out:
                out = self._est_tokens(len(getattr(resp, "completion_text", "") or ""))
            if out:
                self._tok_stats["out"] += out
            self._tok_save()
        except Exception as e:
            self.logger.debug(f"[图恒宇] token 输出统计失败：{e}")

    # ---------- 命令 ----------
    async def _publish_once(self) -> dict:
        """生成并发布一条空间动态。命令与插件页面共用同一条路径。"""
        if self._scheduler is None:
            return {"ok": False, "message": "调度器未运行（插件可能被禁用）。"}
        await self._refresh_persona()
        from .core.llm import generate_moment_text

        st = self._scheduler.schedule.state_at()
        # 关键：把当前人设传进去。不传就会退回通用口吻 → 说说不带人设（老问题）。
        content = await generate_moment_text(
            self.context, self.config, st.now_line(), self._scheduler.persona_text
        )
        if not content:
            return {"ok": False, "message": "内容生成失败：没有可用模型，看日志。", "state": st.brief()}
        ok = await self._scheduler._post_moment(content)
        if ok:
            self._scheduler._last_moment = datetime.now()
            return {"ok": True, "message": "已发布", "content": content, "state": st.brief()}
        return {
            "ok": False,
            "message": "发布失败，看 AstrBot 日志里的 [图恒宇] 行。",
            "content": content,
            "state": st.brief(),
        }

    @filter.command("图恒宇")
    async def status(self, event: AstrMessageEvent):
        """查看插件状态。"""
        if self._scheduler is None:
            yield event.plain_result("[图恒宇] 调度器未运行（插件可能被禁用）。")
            return
        await self._refresh_persona()
        yield event.plain_result(self._scheduler.status_text())

    @filter.command("图恒宇测试")
    async def test_moment(self, event: AstrMessageEvent):
        """立刻手动发一条空间动态，用于验证链路是否打通。"""
        if self._scheduler is None:
            yield event.plain_result("[图恒宇] 调度器未运行。")
            return
        yield event.plain_result("[图恒宇] 正在生成并发布，稍等 ...")
        try:
            r = await self._publish_once()
            if r.get("ok"):
                yield event.plain_result(f"[图恒宇] 已发布（此刻：{r.get('state')}）：{r.get('content')}")
            elif r.get("content"):
                yield event.plain_result("[图恒宇] 发布失败，看 AstrBot 日志里的 [图恒宇] 行。")
            else:
                yield event.plain_result(f"[图恒宇] {r.get('message')}")
        except Exception as e:
            yield event.plain_result(f"[图恒宇] 出错：{e}")

    @filter.command("图恒宇好感")
    async def favour_status(self, event: AstrMessageEvent):
        """查看自己当前的好感度 / 印象 / 关系（只读）。"""
        sec = self._favour_cfg()
        if not sec.get("enabled", True):
            yield event.plain_result("[图恒宇] 好感度系统未启用。")
            return
        uid = str(event.get_sender_id() or "")
        state = self._favour().get(uid, self._scope(event, sec))
        yield event.plain_result(
            f"[图恒宇] 好感度 {state['favour']}｜印象：{state['attitude']}"
            f"｜关系：{state['relationship']}"
        )

    @filter.command("token诊断")
    async def token_diag(self, event: AstrMessageEvent):
        """查看上一次 LLM 请求的 token 构成，以及今日累计用量。"""
        d = self._tok_last
        if not d:
            yield event.plain_result("[图恒宇] token 诊断：本次运行还没捕获到 LLM 请求。")
            return
        sys_t = self._est_tokens(d.get("sys_chars", 0))
        ctx_t = self._est_tokens(d.get("ctx_chars", 0))
        tool_t = self._est_tokens(d.get("tools_chars", 0))
        total = sys_t + ctx_t + tool_t + self._est_tokens(d.get("prompt_chars", 0))
        st = self._tok_stats
        lines = [
            f"[图恒宇] token 诊断（最近一次请求 {d.get('at')}，模型 {d.get('model')}）",
            f"system_prompt：{d.get('sys_chars', 0)} 字符 ≈ {sys_t} token",
            f"上下文：{d.get('ctx_count', 0)} 条 / {d.get('ctx_chars', 0)} 字符 ≈ {ctx_t} token",
            f"工具：{len(d.get('tools') or [])} 个 / {d.get('tools_chars', 0)} 字符 ≈ {tool_t} token",
            f"本次合计 ≈ {total} token",
            f"今日：私聊 {st.get('p_reqs', 0)} 次，输入 ≈ {st.get('p_in', 0)} token",
            f"　　　全部 {st.get('reqs', 0)} 次，输出 ≈ {st.get('out', 0)} token",
        ]
        tools = d.get("tools") or []
        if tools:
            top = "、".join(f"{n}≈{self._est_tokens(c)}" for n, c in tools[:6])
            lines.append(f"工具明细（前 6）：{top}")
        yield event.plain_result("\n".join(lines))


    # ---------- 插件页面 API ----------
    async def page_status(self):
        """GET /astrbot_plugin_tuhengyu/status —— 结构化运行状态。"""
        if self._scheduler is None:
            return json_response({"running": False})
        await self._refresh_persona()
        data = self._scheduler.status_dict()
        data["running"] = True
        return json_response(data)

    async def page_reschedule(self):
        """POST /astrbot_plugin_tuhengyu/reschedule —— 丢弃旧作息并重新生成。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        await self._refresh_persona()  # 先取当前人设，再按它重算
        try:
            await self._scheduler.schedule.regenerate(self.context)
        except Exception as e:
            return error_response(f"重算失败：{e}", status_code=500)
        data = self._scheduler.status_dict()
        data["running"] = True
        return json_response(data)

    async def page_test_moment(self):
        """POST /astrbot_plugin_tuhengyu/test-moment —— 立即发一条（等同 /图恒宇测试）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            result = await self._publish_once()
        except Exception as e:
            return error_response(f"发布出错：{e}", status_code=500)
        data = self._scheduler.status_dict()
        data["running"] = True
        data["result"] = result
        return json_response(data)

    async def page_sticker_reload(self):
        """POST /astrbot_plugin_tuhengyu/sticker-reload —— 重扫表情包目录。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            self._scheduler.stickers.reload()
        except Exception as e:
            return error_response(f"重扫失败：{e}", status_code=500)
        data = self._scheduler.status_dict()
        data["running"] = True
        return json_response(data)

    async def page_stickers(self):
        """GET /astrbot_plugin_tuhengyu/stickers —— 表情包库按标签分组（含 base64 预览）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        lib = self._scheduler.stickers
        try:
            groups = lib.groups_by_intent()
        except Exception as e:
            return error_response(f"读取表情包失败：{e}", status_code=500)

        max_item = 800 * 1024  # 原图直接内联的上限（缩略不可用时的回退）
        max_total = 24 * 1024 * 1024  # 内联总量上限
        max_src = 20 * 1024 * 1024  # 超过此大小的原图不尝试生成缩略
        total = 0
        truncated = False
        out = []
        for label, items in groups.items():
            pairs = sorted(items, key=lambda tp: tp[1].name)
            images = []
            for tag, p in pairs:
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                item = {"name": p.name, "size": size, "tag": tag}
                if total >= max_total:
                    item["skipped"] = True
                    truncated = True
                    images.append(item)
                    continue
                # ① 优先缩略图（大多数图都能看，且响应小）
                thumb = thumb_b64(p) if size <= max_src else None
                if thumb:
                    b64, w, h = thumb
                    item["b64"] = b64
                    item["thumb"] = True
                    item["w"] = w
                    item["h"] = h
                    total += int(len(b64) * 0.75)
                    images.append(item)
                    continue
                # ② 回退：小图直接内联原图
                if size <= max_item:
                    raw = read_base64(p)
                    if raw:
                        item["b64"] = raw
                        total += size
                    else:
                        item["error"] = "读取失败"
                else:
                    item["skipped"] = True
                    truncated = True
                images.append(item)
            out.append({"label": label, "count": len(pairs), "images": images})

        return json_response(
            {
                "groups": out,
                "categories": lib.categories(),
                "desc": lib.describe(),
                "total_bytes": total,
                "truncated": truncated,
                "max_item": max_item,
            }
        )

    async def page_sticker_category(self):
        """POST /astrbot_plugin_tuhengyu/sticker-category —— 新建一个表情包分类（子目录）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        name = str((body or {}).get("name", "")).strip()
        ok, msg = self._scheduler.stickers.add_category(name)
        if not ok:
            return error_response(msg, status_code=400)
        data = self._scheduler.status_dict()
        data["running"] = True
        data["message"] = msg
        return json_response(data)

    async def page_sticker_upload(self):
        """POST /astrbot_plugin_tuhengyu/sticker-upload —— 上传一张图到指定分类（base64）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        import base64

        category = str((body or {}).get("category", "")).strip()
        filename = str((body or {}).get("filename", "")).strip()
        raw = (body or {}).get("data", "")
        try:
            data_bytes = base64.b64decode(raw) if raw else b""
        except Exception:
            data_bytes = b""
        ok, msg = self._scheduler.stickers.save_image(category, filename, data_bytes)
        if not ok:
            return error_response(msg, status_code=400)
        out = self._scheduler.status_dict()
        out["running"] = True
        out["message"] = msg
        return json_response(out)

    async def page_sticker_classify(self):
        """POST /astrbot_plugin_tuhengyu/sticker-classify —— 识图把散图归入意图类目。

        对 default / collected 下的图逐张调一次多模态模型（消耗 token，只在这里发生）。
        用户自建分类名也作为候选类目参与判定；判为「其他」的原样不动。
        """
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        lib = self._scheduler.stickers
        exclude = set(intent_labels()) | set(SYSTEM_LABELS)
        extra = [c for c in lib.categories() if c not in exclude]
        try:
            provider = self.context.get_using_provider()
        except Exception as e:
            self.logger.warning(f"[图恒宇] 取模型失败：{e}")
            provider = None
        if provider is None:
            return error_response("未配置对话模型，无法识图归类", status_code=400)
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        try:
            limit = int((body or {}).get("limit", 6))
        except (TypeError, ValueError):
            limit = 6
        if limit <= 0:
            limit = 6
        targets = lib.classify_targets()
        batch = targets[:limit]
        moved, kept, failed = 0, 0, 0
        for _tag, path in batch:
            cat = await classify_image(provider, path, extra=extra)
            if cat == INTENT_FALLBACK:
                kept += 1
                continue
            ok, _msg = lib.move_image(path, cat)
            if ok:
                moved += 1
            else:
                failed += 1
        remaining = len(lib.classify_targets())
        data = self._scheduler.status_dict()
        data["running"] = True
        data["classify"] = {
            "total": len(targets),
            "batch": len(batch),
            "moved": moved,
            "kept": kept,
            "failed": failed,
            "remaining": remaining,
        }
        data["message"] = (
            f"本批 {len(batch)} 张：归类 {moved}，留在「其他」{kept}，失败 {failed}；"
            f"尚有 {remaining} 张未处理"
        )
        return json_response(data)

    # ---------- 插件页面：设置读写 ----------
    def _load_schema(self) -> dict:
        """读插件同级的 _conf_schema.json（设置页据此渲染控件）。"""
        import json
        import os

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"[图恒宇] 读取 _conf_schema.json 失败：{e}")
            return {}

    def _config_values(self) -> dict:
        """当前配置的纯数据副本（保证可 JSON 序列化）。"""
        import json

        try:
            return json.loads(json.dumps(dict(self.config), ensure_ascii=False, default=str))
        except Exception:
            return {}

    @staticmethod
    def _coerce(value, sch):
        """按 schema 的 type 归一化单值。"""
        typ = (sch or {}).get("type")
        if typ == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on", "是", "开")
        if typ == "int":
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
        if typ == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        return "" if value is None else str(value)

    def _merge_settings(self, payload: dict) -> dict:
        """只接受 schema 里声明过的键，其余忽略（防写坏配置）。"""
        import json

        schema = self._load_schema()
        out = json.loads(json.dumps(dict(self.config), ensure_ascii=False, default=str))
        for key, sch in schema.items():
            if key not in payload:
                continue
            val = payload[key]
            if (sch or {}).get("type") == "object":
                if not isinstance(val, dict):
                    continue
                cur = out.get(key)
                if not isinstance(cur, dict):
                    cur = {}
                for sub, subsch in ((sch or {}).get("items") or {}).items():
                    if sub in val:
                        cur[sub] = self._coerce(val[sub], subsch)
                out[key] = cur
            else:
                out[key] = self._coerce(val, sch)
        return out

    async def _collect_options(self) -> dict:
        """下拉选项：可用人格 + 可用模型提供商。"""
        personas = []
        pm = getattr(self.context, "persona_manager", None)
        if pm is not None:
            try:
                for p in await pm.get_all_personas():
                    pid = str(getattr(p, "persona_id", "") or "")
                    name = str(getattr(p, "name", "") or "")
                    if pid:
                        personas.append({"id": pid, "name": name or pid})
            except Exception as e:
                self.logger.warning(f"[图恒宇] 取人格列表失败：{e}")
        providers = []
        try:
            for prv in self.context.get_all_providers():
                pid = ""
                model = ""
                try:
                    m = prv.meta()
                    pid = str(getattr(m, "id", "") or "")
                    model = str(getattr(m, "model", "") or "")
                except Exception:
                    pass
                if not pid:
                    try:
                        pid = str((getattr(prv, "provider_config", {}) or {}).get("id", "") or "")
                    except Exception:
                        pid = ""
                if pid:
                    providers.append({"id": pid, "name": f"{pid}（{model}）" if model else pid})
        except Exception as e:
            self.logger.warning(f"[图恒宇] 取模型列表失败：{e}")
        return {"persona": personas, "provider": providers}

    async def page_settings_get(self):
        """GET /astrbot_plugin_tuhengyu/settings —— schema + 当前值 + 下拉选项。"""
        return json_response(
            {
                "schema": self._load_schema(),
                "values": self._config_values(),
                "options": await self._collect_options(),
            }
        )

    async def page_settings_post(self):
        """POST /astrbot_plugin_tuhengyu/settings —— 保存设置（body = 完整值对象）。"""
        try:
            payload = await web_request.json({})
        except Exception as e:
            return error_response(f"读取请求体失败：{e}", status_code=400)
        if not isinstance(payload, dict) or not payload:
            return error_response("请求体不是有效的设置对象", status_code=400)
        try:
            merged = self._merge_settings(payload)
        except Exception as e:
            return error_response(f"设置格式错误：{e}", status_code=400)
        try:
            self.config.update(merged)
            save = getattr(self.config, "save_config", None)
            if callable(save):
                save()
        except Exception as e:
            return error_response(f"保存失败：{e}", status_code=500)
        await self._refresh_persona()  # 人设/模型可能改了
        data = self._scheduler.status_dict() if self._scheduler is not None else {}
        data["running"] = self._scheduler is not None
        return json_response({"ok": True, "values": self._config_values(), "status": data})
        return json_response(data)