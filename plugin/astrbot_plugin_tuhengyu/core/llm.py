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


def _section(config: dict, name: str) -> dict:
    """安全取嵌套配置段。schema 里的 object 会存成嵌套 dict。"""
    v = config.get(name) if isinstance(config, dict) else None
    return v if isinstance(v, dict) else {}


def with_state(prompt: str, state_line: str) -> str:
    """把「此刻在干嘛」拼到指令尾部。没给状态就原样返回。"""
    line = (state_line or "").strip()
    if not line:
        return prompt
    return f"{prompt}\n\n此刻你{line}，内容要跟这个时刻对得上。"


async def generate_moment_text(context, config: dict, state_line: str = "") -> str:
    """生成一条说说内容。失败返回空串。

    state_line：来自作息的「此刻」描述。有它，内容才不是凭空写的。
    """
    moment = _section(config, "moment")
    provider_id = await resolve_provider_id(
        context, str(moment.get("provider_id", "")).strip()
    )
    if not provider_id:
        logger.warning("[图恒宇] 没有可用的对话模型，跳过发空间。")
        return ""

    system_prompt = str(config.get("persona_prompt", "")).strip() or DEFAULT_SYSTEM_PROMPT
    prompt = with_state(str(moment.get("prompt", "")).strip() or DEFAULT_PROMPT, state_line)

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


# ---------- 作息生成 ----------

SCHEDULE_SYSTEM_PROMPT = (
    "你在帮一个角色设计作息表。只输出 JSON，不要解释，不要 markdown 代码块。"
)

SCHEDULE_PROMPT = """按下面这个人设，排出他/她一天 24 小时的作息。

人设：
{persona}

要求：
- 覆盖 24 小时，时段首尾相接，不重叠、不留空
- 每段给：start、end（HH:MM，24 小时制）、scene（在干什么，一句话）、state（什么心情，一两个词）、awake（醒着 true / 睡着 false）
- scene 和 state 要贴人设，别写成「工作」「休息」这种干巴巴的词
- 至少一段 awake 为 false（要睡觉）

只输出 JSON，格式：
{{"periods": [{{"start": "07:30", "end": "09:00", "scene": "...", "state": "...", "awake": true}}]}}"""


async def generate_schedule_text(context, persona: str, configured_id: str = "") -> str:
    """让模型按人设推一份作息 JSON。失败返回空串。"""
    provider_id = await resolve_provider_id(context, configured_id)
    if not provider_id:
        logger.warning("[图恒宇] 没有可用的模型，无法生成作息。")
        return ""
    try:
        resp = await context.llm_generate(
            chat_provider_id=provider_id,
            prompt=SCHEDULE_PROMPT.format(persona=persona),
            system_prompt=SCHEDULE_SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.warning(f"[图恒宇] 生成作息失败：{e}")
        return ""
    return getattr(resp, "completion_text", "") or ""