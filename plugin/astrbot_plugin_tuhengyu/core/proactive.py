"""群聊主动插话：醒着的时候，偶尔接一句群友的话。

口径（博士 2026-10-02 定）：

    群聊里就像普通成员一样插嘴，接群友的话说
        不做「冷场才说话」那套，热聊里也接
    只要人醒着才能说话
    概率极低

防刷屏不靠内容判据，靠三条硬上限：冷却、每群每日上限、一次循环最多发一句。

生成内容走模型，人设拼进 user 消息（0.2.19 规范：长人设只放 system 会被无视）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Decision:
    act: bool
    reason: str


def decide_proactive(
    *,
    awake: bool = True,
    cooling: bool = False,
    daily_count: int = 0,
    daily_cap: int = 8,
    recent_count: int = 0,
    min_recent: int = 3,
    prob: float = 0.05,
    rng: random.Random | None = None,
) -> Decision:
    """决定这次要不要插一句。纯函数，可单测。"""
    r = rng or random
    if not awake:
        return Decision(False, "睡着")
    if daily_cap > 0 and daily_count >= daily_cap:
        return Decision(False, "今日已达上限")
    if cooling:
        return Decision(False, "冷却中")
    if recent_count < min_recent:
        return Decision(False, "群里没什么可接的话")
    if r.random() >= max(0.0, float(prob)):
        return Decision(False, "这次没轮到")
    return Decision(True, "插一句")


DEFAULT_PROMPT = (
    "群里正聊着，你看到了最近的几句。"
    "挑一个能接上的点，用你自己的口吻插一句，像群里普通成员那样。"
    "接不上就不说；可以短、可以随口、也可以半开玩笑。"
)


def build_proactive_prompt(
    *,
    persona: str = "",
    lines: list | None = None,
    scene: str = "",
    state: str = "",
    max_chars: int = 20,
) -> str:
    """给模型出题：接一句。人设拼进 user 消息，不走 system。"""
    convo = "\n".join([str(x) for x in (lines or [])]) or "（暂时没有可接的话）"
    where = f"你此刻{scene}，心情{state}。" if scene else ""
    body = (
        f"群里最近的发言（这就是你要接的内容）：\n{convo}\n\n"
        f"{where}群里正聊着。\n"
        "用你自己的口吻插一句，必须接上面某一条具体的话——可以回应某个人，"
        "也可以顺着某个话题补一句。不要聊上面没出现过的话题，别用客服腔，别用通用客套话。\n"
        f"只输出这一句话本身：不超过 {max_chars} 个汉字，不加引号，不加动作描写，"
        "不加括号说明，不用说自己是 AI。实在接不上，就只输出一个「-」。"
    )
    p = str(persona or "").strip()
    if p:
        return f"{p}\n\n——按上面这个角色——\n{body}"
    return body
