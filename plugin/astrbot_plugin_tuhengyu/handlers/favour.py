"""好感度：注入与回收。"""

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


class FavourHandlers:

    # ---------- 好感度：注入 + 回收 ----------
    def _favour_cfg(self) -> dict:
        return self._sec("favour")

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
