"""设置读写：schema 加载、取值、回落、合并。"""

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


# 插件根目录 = 本文件目录（web/）的上一级。
# ⚠️ 本模块在子目录里，取插件内文件必须用这个基准，不能用 __file__ 的 dirname（会落到 web/）。
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SettingsHandlers:

    # ---------- 插件页面：设置读写 ----------
    def _load_schema(self) -> dict:
        """读插件根目录的 _conf_schema.json（设置页据此渲染控件）。"""

        path = os.path.join(PLUGIN_ROOT, "_conf_schema.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"[图恒宇] 读取 _conf_schema.json 失败：{e}")
            return {}

    def _config_values(self) -> dict:
        """当前配置的纯数据副本（保证可 JSON 序列化）。"""

        try:
            return json.loads(json.dumps(dict(self.config), ensure_ascii=False, default=str))
        except Exception:
            return {}

    @staticmethod
    def _coerce(value, sch):
        """按 schema 的 type 归一化单值。

        空值（None / 空白串）不写 0，而是回落 schema 默认值 —— 用户在设置页
        把一个数值输入框清空，应当恢复默认，而不是被静默改成 0。
        """
        sch = sch or {}
        typ = sch.get("type")
        default = sch.get("default")
        blank = value is None or (isinstance(value, str) and not value.strip())

        def _fallback_num(zero):
            if isinstance(default, (int, float)) and not isinstance(default, bool):
                return type(zero)(default)
            return zero

        if typ == "bool":
            if isinstance(value, bool):
                return value
            if blank:
                return bool(default) if default is not None else False
            return str(value).strip().lower() in ("1", "true", "yes", "on", "是", "开")
        if typ == "int":
            if blank:
                return _fallback_num(0)
            try:
                return int(value)
            except (TypeError, ValueError):
                return _fallback_num(0)
        if typ == "float":
            if blank:
                return _fallback_num(0.0)
            try:
                return float(value)
            except (TypeError, ValueError):
                return _fallback_num(0.0)
        if blank:
            return default if default is not None else ""
        return str(value)

    def _merge_settings(self, payload: dict) -> dict:
        """只接受 schema 里声明过的键，其余忽略（防写坏配置）。"""

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
