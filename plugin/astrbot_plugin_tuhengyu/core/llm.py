"""内容生成 —— 让「发空间」有东西可发。

走 AstrBot 的模型能力（context.llm_generate），不自己接 API。
这样用户在 AstrBot 里配好模型，插件就自动能用，不需要再填一次 key。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("astrbot")

DEFAULT_SYSTEM_PROMPT = (
    "你是一个有自己生活节奏的人，正在发 QQ 空间动态。"
    "说人话，口语一点，像随手记下来的心情或见闻。"
    "不要提自己是 AI，不要用客服腔，不要加话题标签，不要加引号。"
)

DEFAULT_PROMPT = (
    "写一条 QQ 空间说说，20 到 60 字，内容随意，是此刻的所见所想。"
    "只输出正文，不要任何前后缀说明。"
)


async def resolve_provider_id(context, configured_id: str = "") -> str:
    """确定用哪个模型。优先插件配置，否则用 AstrBot 当前默认。"""
    if configured_id:
        return configured_id
    try:
        prov = context.get_using_provider()
    except Exception:
        prov = None
    if prov is None:
        return ""
    return getattr(prov, "provider_config", {}).get("id") or getattr(prov, "id", "") or ""


async def generate_moment_text(context, config: dict) -> str:
    """生成一条说说内容。失败返回空串。"""
    provider_id = await resolve_provider_id(context, str(config.get("llm_provider_id", "")).strip())
    if not provider_id:
        logger.warning("[图恒宇] 没有可用的对话模型，跳过发空间。")
        return ""

    system_prompt = str(config.get("persona_prompt", "")).strip() or DEFAULT_SYSTEM_PROMPT
    prompt = str(config.get("moment_prompt", "")).strip() or DEFAULT_PROMPT

    try:
        resp = await context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt,
            system_prompt=system_prompt,
        )
    except Exception as e:
        logger.warning(f"[图恒宇] 生成说说内容失败：{e}")
        return ""

    text = getattr(resp, "completion_text", "") or ""
    text = text.strip().strip('"').strip()
    if len(text) > 200:
        text = text[:200]
    return text