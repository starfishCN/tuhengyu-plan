"""戳一戳反应：按人设 + 好感 + 状态 + 频次决定怎么应。

不写死「问」或「戳回去」——真人也不是二选一：

    冷却中（同人同会话刚戳过） → 不理
    同一人短时间连戳到阈值     → 怼一句
    睡眠时段（作息里 awake=false）→ 不理
    好感高（关系好）           → 回戳，多数再补一句话
    好感低（反感/敌对）        → 多半不理，偶尔冷一句
    普通关系                   → 回戳和问一句，抛硬币

文字部分交给模型（人设驱动）；拿不到模型时退回内置短句，保证有反应。
回戳走 Poke 消息组件，失败不影响文字。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

IGNORE = "ignore"
SILENT_POKE = "silent_poke"  # 只回戳，不说话
TEXT = "text"  # 只说一句
BOTH = "both"  # 回戳 + 说话
SNAP = "snap"  # 怼一句

_POKE_BACK_KINDS = (SILENT_POKE, BOTH, SNAP)
_SPEAK_KINDS = (TEXT, BOTH, SNAP)


@dataclass
class Reaction:
    kind: str
    reason: str

    def poke_back(self) -> bool:
        return self.kind in _POKE_BACK_KINDS

    def speak(self) -> bool:
        return self.kind in _SPEAK_KINDS


def decide(
    *,
    favour: int,
    awake: bool = True,
    repeat: int = 0,
    cooling: bool = False,
    poke_back_prob: float = 0.6,
    snap_threshold: int = 3,
    friendly_at: int = 40,
    cold_at: int = -10,
    rng: random.Random | None = None,
) -> Reaction:
    """决定这次怎么应。纯函数，可单测。"""
    r = rng or random
    if cooling:
        return Reaction(IGNORE, "冷却中")
    if snap_threshold > 0 and repeat >= snap_threshold:
        return Reaction(SNAP, "同一人连戳")
    if not awake:
        return Reaction(IGNORE, "睡着了")
    if favour >= friendly_at:
        return Reaction(BOTH if r.random() < 0.75 else SILENT_POKE, "关系好")
    if favour < cold_at:
        return Reaction(IGNORE if r.random() < 0.6 else TEXT, "关系差")
    return Reaction(SILENT_POKE if r.random() < poke_back_prob else TEXT, "普通关系")


# ---------- 无模型时的回落台词 ----------

FALLBACK = {
    "snap": ["别戳了", "手别乱动", "戳什么戳", "再戳就拉黑你"],
    "snap_asleep": ["……困着呢", "别闹，睡了"],
    "text_friendly": ["在呢，怎么啦", "嗯？找我", "怎么啦～"],
    "text_cold": ["？", "有事说事", "别戳"],
    "text_normal": ["？", "干嘛", "在呢", "有事？"],
}


def fallback_text(
    reaction: Reaction,
    *,
    favour: int,
    awake: bool = True,
    group: bool = False,
    friendly_at: int = 40,
    cold_at: int = -10,
) -> str:
    """回落台词池。群聊取更短的。"""
    if reaction.kind == SNAP:
        pool = FALLBACK["snap_asleep"] if not awake else FALLBACK["snap"]
    elif reaction.kind in (TEXT, BOTH):
        if favour >= friendly_at:
            pool = FALLBACK["text_friendly"]
        elif favour < cold_at:
            pool = FALLBACK["text_cold"]
        else:
            pool = FALLBACK["text_normal"]
    else:
        return ""
    line = random.choice(pool)
    return line


POKE_SYSTEM_HINT = (
    "你不是客服。你被同一个人戳了一下，按你此刻的心情回应一句。"
)


def build_poke_prompt(
    *,
    kind: str,
    favour: int,
    relationship: str,
    attitude: str,
    scene: str = "",
    state: str = "",
    group: bool = False,
    name: str = "",
) -> str:
    """给模型出题：一句话，贴人设。"""
    limit = 20 if group else 30
    if kind == SNAP:
        mood = "你已经被同一个人连着戳烦了，直接怼一句，短、带情绪、不带脏字。"
    elif favour >= 40:
        mood = "这是你比较在意的人，语气可以软一点、亲近一点。"
    elif favour < -10:
        mood = "你对这人不太待见，冷淡或敷衍。"
    else:
        mood = "普通关系，随口应一句就行。"
    who = f"（称呼：{name}）" if name else ""
    where = f"你此刻{scene}，心情{state}。" if scene else ""
    return (
        f"事件：有人在 QQ 上戳了你一下{who}。\n"
        f"你和他的关系：{relationship}；你对他印象：{attitude}；好感度：{favour}。\n"
        f"{where}{mood}\n"
        f"只输出这一句话本身：不超过 {limit} 个汉字，不加引号，不加动作描写，"
        "不加括号说明，不用说自己是 AI。"
    )
