"""群聊主动插话：观察、判定、状态落盘。"""

import asyncio
import json
import os
import random
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Image, Poke
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request as web_request
from ..core.classify import classify_image
from ..core.favour import FavourStore, build_injection, parse_state_marker
from ..core.intent import FALLBACK as INTENT_FALLBACK
from ..core.intent import labels as intent_labels
from ..core.persona import resolve_persona
from ..core.proactive import build_proactive_prompt, decide_proactive
from ..core.poke import IGNORE as POKE_IGNORE
from ..core.poke import build_poke_prompt, decide as decide_poke, fallback_text
from ..core.scheduler import LifeScheduler
from ..core.stickers import SYSTEM_LABELS, read_base64, save_collected, thumb_b64


class ProactiveHandlers:

    # ---------- 群聊主动插话 ----------
    def _proactive_cfg(self) -> dict:
        return self._sec("proactive")

    def _proactive_path(self) -> str:
        return self._data_file("proactive.json")

    def _proactive_load(self) -> None:
        """读回每群的冷却 / 今日计数（群聊内容本身不落盘）。"""

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
