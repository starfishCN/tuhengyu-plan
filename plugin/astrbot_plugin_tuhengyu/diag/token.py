"""token 诊断：估算、快照、输出。"""

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


class TokenHandlers:

    # ---------- token 诊断 ----------
    # 折算口径：中文 1 token ≈ 2.06 字符（实测 7994 字符 ≈ 3876 token）。
    _TOKEN_CHARS = 2.06

    def _est_tokens(self, chars) -> int:
        try:
            return int(round(int(chars or 0) / self._TOKEN_CHARS))
        except Exception:
            return 0

    def _tok_path(self) -> str:
        return self._data_file("token_stats.json")

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

        blank = self._tok_blank()
        try:
            if os.path.exists(self._tok_path()):
                with open(self._tok_path(), encoding="utf-8-sig") as f:
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
