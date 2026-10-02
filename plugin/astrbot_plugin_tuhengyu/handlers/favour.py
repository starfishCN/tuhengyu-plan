"""好感度：注入与回收。

三块状态：
    favour.json         当前三维状态（含昵称 / 更新时间）
    favour_history.json 好感度历史采样（画折线用）
    favour_curve.json  人设驱动、LLM 生成的「变化曲线」参数

曲线生成是懒加载 + 指纹缓存：只有在人设变了（指纹不同）时才再调一次模型，
平时读盘即用，不烧 token。生成失败 / 未启用一律回落内置默认参数。
"""

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
from ..core.favour import (
    CurveStore,
    FavourStore,
    HistoryStore,
    build_injection,
    parse_curve_json,
    parse_state_marker,
    persona_fingerprint,
    sanitize_contexts,
)
from ..core.intent import FALLBACK as INTENT_FALLBACK
from ..core.intent import labels as intent_labels
from ..core.llm import generate_curve_text
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
        if getattr(self, "_favour_store", None) is None:
            self._favour_store = FavourStore(self._data_dir())
        return self._favour_store

    def _history(self) -> HistoryStore:
        if getattr(self, "_favour_history", None) is None:
            self._favour_history = HistoryStore(self._data_dir())
        return self._favour_history

    def _curve_store(self) -> CurveStore:
        if getattr(self, "_favour_curve_store", None) is None:
            self._favour_curve_store = CurveStore(self._data_dir())
        return self._favour_curve_store

    def _scope(self, event: AstrMessageEvent, sec: dict) -> str | None:
        """会话独立开关；关着返回 None（全局状态）。"""
        if not sec.get("session_based", False):
            return None
        try:
            return str(event.unified_msg_origin or "") or None
        except Exception:
            return None

    async def _ensure_curve(self) -> dict:
        """取当前曲线；仅当人设指纹变化时才重新调 LLM 生成。

        失败 / 无人设 → 原样返回已有曲线（默认参数兜底），不抛。
        """
        store = self._curve_store()
        cur = store.get()
        sec = self._favour_cfg()
        if sec.get("curve_enabled", True) is False:
            return cur
        try:
            persona, _label, _name = await resolve_persona(self.context, self.config)
        except Exception:
            persona = ""
        if not persona:
            return cur
        fp = persona_fingerprint(persona)
        if cur.get("source") == "llm" and cur.get("persona_fingerprint") == fp:
            return cur
        try:
            text = await generate_curve_text(
                self.context, persona, str(sec.get("curve_model", "")).strip()
            )
        except Exception as e:
            self.logger.warning(f"[图恒宇] 生成好感度曲线失败：{e}")
            return cur
        raw = parse_curve_json(text)
        if not raw:
            self.logger.warning("[图恒宇] 好感度曲线解析失败，沿用已有参数。")
            return cur
        return store.set(raw, fp, "llm")

    @filter.on_llm_request()
    async def inject_favour(self, event: AstrMessageEvent, req: ProviderRequest):
        """把当前三维状态与更新指令追加到 system prompt。"""
        self._tok_snapshot(event, req)
        # 历史里残留的旧状态行会被模型照抄，导致手动改过的数值被拉回。
        # 这里只清上下文里的行，不动 system prompt（指令行本身含标记）。
        try:
            n = sanitize_contexts(req.contexts)
            if n:
                self.logger.debug(f"[图恒宇] 已清理历史中 {n} 处状态行残留。")
        except Exception as e:
            self.logger.warning(f"[图恒宇] 清理历史状态行失败：{e}")
        sec = self._favour_cfg()
        if not sec.get("enabled", True) or not sec.get("inject", True):
            return
        try:
            uid = str(event.get_sender_id() or "")
            if not uid:
                return
            curve = await self._ensure_curve()
            state = self._favour().get(uid, self._scope(event, sec))
            req.system_prompt = (req.system_prompt or "") + build_injection(state, curve)
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
            if not uid:
                return
            scope = self._scope(event, sec)
            store = self._favour()
            key = FavourStore.key(uid, scope)
            # 手改保护：窗口内模型不得改写被手动编辑过的文本字段（好感度不受限，
            # 那个本来就该随互动走）。窗口长度由 manual_hold_hours 配置，0 = 关闭。
            held = store.manual_hold(key, sec.get("manual_hold_hours", 24))
            if held:
                blocked = [f for f in held if f in patch]
                for f in blocked:
                    patch.pop(f, None)
                if blocked:
                    self.logger.info(
                        f"[图恒宇] {key} 的印象/关系在手改保护期内，已忽略模型对 {blocked} 的改写。"
                    )
            if not any(f in patch for f in ("favour", "attitude", "relationship")):
                return
            state = store.update(uid, patch, scope, name=self._sender_name(event))
            # 值有变才记历史（HistoryStore 内部再判一次），供折线图使用
            if "favour" in patch:
                self._history().record(
                    FavourStore.key(uid, scope),
                    state.get("favour", 0),
                    state.get("attitude", ""),
                    state.get("relationship", ""),
                )
        except Exception as e:
            self.logger.warning(f"[图恒宇] 回收好感度失败：{e}")

    @staticmethod
    def _sender_name(event: AstrMessageEvent) -> str:
        """尽量取发送者显示名，取不到返回空串（页签里回落显示 QQ）。"""
        try:
            name = event.get_sender_name()
            if name:
                return str(name).strip()[:40]
        except Exception:
            pass
        try:
            sender = getattr(event, "message_obj", None)
            sender = getattr(sender, "sender", None)
            nick = getattr(sender, "nickname", None)
            if nick:
                return str(nick).strip()[:40]
        except Exception:
            pass
        return ""
