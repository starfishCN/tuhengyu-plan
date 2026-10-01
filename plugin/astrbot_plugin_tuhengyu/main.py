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
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request as web_request

from .core.persona import resolve_persona
from .core.scheduler import LifeScheduler
from .core.stickers import read_base64, save_collected, thumb_b64

# Web API 路由必须以插件名为前缀（AstrBot 约定，2026-10-01 核对官方文档）。
PLUGIN_NAME = "astrbot_plugin_tuhengyu"


class TuhengyuPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.config = config or {}
        self._scheduler = None
        self._task = None
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
                "插件页面：表情包库（按标签分组）",
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
        path = self._scheduler.pick_sticker(f"{st.scene}{st.state}{reply_text}")
        if path is None:
            return
        b64 = read_base64(path)
        if not b64:
            return
        from astrbot.api.message_components import Image

        result.chain.append(Image.fromBase64(b64))

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
            groups = lib.groups()
        except Exception as e:
            return error_response(f"读取表情包失败：{e}", status_code=500)

        max_item = 800 * 1024  # 原图直接内联的上限（缩略不可用时的回退）
        max_total = 24 * 1024 * 1024  # 内联总量上限
        max_src = 20 * 1024 * 1024  # 超过此大小的原图不尝试生成缩略
        total = 0
        truncated = False
        out = []
        for label in sorted(groups):
            paths = sorted(groups[label], key=lambda p: p.name)
            images = []
            for p in paths:
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                item = {"name": p.name, "size": size}
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
            out.append({"label": label, "count": len(paths), "images": images})

        return json_response(
            {
                "groups": out,
                "desc": lib.describe(),
                "total_bytes": total,
                "truncated": truncated,
                "max_item": max_item,
            }
        )

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