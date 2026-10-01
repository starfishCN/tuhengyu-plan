"""识图归类：把一张图交给多模态模型，判它属于哪个类目。

只在用户点「自动归类」时调用 —— 每张图消耗一次多模态请求。
选图（bot 回复附图）不走这里，见 core/stickers.py。

模型只许从给定类目清单里挑一个；返回文本按清单匹配，匹配不上归「其他」。
"""
from __future__ import annotations

import logging

from .intent import FALLBACK
from .intent import labels as intent_labels

logger = logging.getLogger("astrbot")

_PROMPT = (
    "看图，判断这张表情包最适合用在什么场合。"
    "从下面的类目里选恰好一个，只输出类目名本身，不要解释、不要标点。\n"
    "可选类目：{labels}"
)


def _candidates(extra=None) -> list[str]:
    """候选类目 = 内置意图 8 类 + 用户自建分类（去掉「其他」）。"""
    cats = [c for c in intent_labels() if c != FALLBACK]
    for c in (extra or []):
        c = str(c or "").strip()
        if c and c not in cats and c != FALLBACK:
            cats.append(c)
    return cats


def build_prompt(extra=None) -> str:
    return _PROMPT.format(labels=" / ".join(_candidates(extra)))


def parse_reply(text: str, extra=None) -> str:
    """从模型回复里取类目名；取不到返回「其他」。"""
    cats = _candidates(extra)
    s = str(text or "").strip()
    if s in cats:
        return s
    # 子串命中：按名字长度降序，避免短名误伤长名
    for c in sorted(cats, key=len, reverse=True):
        if c in s:
            return c
    return FALLBACK


async def classify_image(provider, path, extra=None) -> str:
    """调一次多模态模型给图片定类目；失败返回「其他」。"""
    if provider is None:
        return FALLBACK
    try:
        resp = await provider.text_chat(
            prompt=build_prompt(extra),
            image_urls=[str(path)],
        )
        text = getattr(resp, "completion_text", "") or ""
        return parse_reply(text, extra)
    except Exception as e:
        logger.warning(f"[图恒宇] 识图归类失败（{path}）：{e}")
        return FALLBACK