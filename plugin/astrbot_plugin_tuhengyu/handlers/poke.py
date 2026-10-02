"""戳一戳：判定、文本生成、回戳。"""

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


class PokeHandlers:

    # ---------- 戳一戳 ----------
    def _poke_cfg(self) -> dict:
        return self._sec("poke")

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
        # 协议端会把「bot 自己戳出去」的动作也回传成一条事件，sender 即 bot 自身。
        # 不拦的话，每次回戳都会多出一条回复（真机实测：一次戳 → 两条，一条带人设一条不带）。
        try:
            self_id = str(event.get_self_id() or "")
        except Exception:
            self_id = ""
        if self_id and uid == self_id:
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
