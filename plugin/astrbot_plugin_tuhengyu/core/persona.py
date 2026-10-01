"""人设来源解析。

优先级：
    1. 插件配置里的 `persona_id`（下拉选定的人格）→ 取该人格正文；
    2. 否则跟随 AstrBot 当前默认人格（换了人格自动生效）；
    3. 再叠加插件配置里的 `persona_prompt`（补充文本，可选）；
    4. 都没有 → 空串，调用方回落内置口吻。

注意：AstrBot 里「换人格」改的是它自己的 persona；插件不再自带一份正文，
只在这里解析，避免两处各写一份、换了这边那边不动。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("astrbot")


def _get(persona, key: str) -> str:
    """Personality 是 TypedDict，但为兼容对象写法两种都取。"""
    if not persona:
        return ""
    try:
        if isinstance(persona, dict):
            return str(persona.get(key, "") or "").strip()
        return str(getattr(persona, key, "") or "").strip()
    except Exception:
        return ""


async def resolve_persona(context, config: dict | None = None) -> tuple[str, str, str]:
    """解析当前生效的人设。

    返回 (人设正文, 来源标签, 人格名)。任何异常都不抛，只回落。
    """
    cfg = config or {}
    pid = str(cfg.get("persona_id", "") or "").strip()
    extra = str(cfg.get("persona_prompt", "") or "").strip()

    text = ""
    name = ""
    label = ""
    pm = getattr(context, "persona_manager", None)
    if pm is not None:
        try:
            persona = None
            if pid:
                persona = pm.get_persona_v3_by_id(pid)
            if persona is None:
                persona = await pm.get_default_persona_v3()
                pid = ""
            text = _get(persona, "prompt")
            name = _get(persona, "name")
            if name:
                label = f"人格「{name}」" + ("（指定）" if pid else "（跟随默认）")
            else:
                label = "人格（跟随默认）"
        except Exception as e:
            logger.warning(f"[图恒宇] 读取 AstrBot 人格失败：{e}")

    if extra:
        text = f"{text}\n{extra}".strip() if text else extra
        label = f"{label} + 插件补充" if label else "插件补充"

    return text, label, name
