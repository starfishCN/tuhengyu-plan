"""好感度：三维内心状态（好感 / 印象 / 关系）。

自研，不接第三方。三处取舍（针对第三方插件「状态块剥离不干净」的老 bug）：
    1. 模型只在回复末尾留**一行**状态行，格式 `%%FAV%% <好感> | <印象> | <关系>`；
    2. 解析时收全部匹配、整行全量剥离，缺字段保持原值；
       —— 块里没有方括号结构，碎块残留不可能发生。
    3. 好感度是**绝对值**（-100 ~ 100），不是增量；当前值每轮注入给模型。

存盘：<插件数据目录>/favour.json
    {"<键>": {"favour": 0, "attitude": "中立", "relationship": "陌生人"}}
键 = 用户 QQ；开启会话独立时 = "<会话标识>_<用户 QQ>"。
"""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger("astrbot")

MARKER = "%%FAV%%"

DEFAULT_STATE: dict = {"favour": 0, "attitude": "中立", "relationship": "陌生人"}

# 找出行内的状态行（同一回复里允许出现多行，全部收走）
_MARKER_FIND = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"([^\n]*)", re.M)
# 剥离：连行尾换行一起吃掉，避免留下空行
_MARKER_STRIP = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[^\n]*\n?", re.M)

BANDS = (
    (75, "亲密信赖", "热情、主动、亲近，可以用亲昵的称呼"),
    (40, "友好", "积极、乐于搭话、带点好情绪"),
    (-10, "中立礼貌", "客气、保持距离、话说得标准"),
    (-50, "反感", "冷淡、简短、不耐烦，能敷衍就敷衍"),
    (-999, "厌恶敌对", "极短、带刺，不想搭理"),
)


def band(favour: int) -> tuple[str, str]:
    """好感度 → (区间名, 语气要求)。"""
    for threshold, name, desc in BANDS:
        if favour >= threshold:
            return name, desc
    return BANDS[-1][1], BANDS[-1][2]


def parse_state_marker(text: str) -> tuple[str, dict | None]:
    """从回复里收走所有状态行。

    返回 (给用户看的正文, 状态更新 dict 或 None)。更新只覆盖解析到的字段。
    """
    if not text or MARKER not in text:
        return text, None
    update: dict = {}
    for m in _MARKER_FIND.finditer(text):
        parts = [p.strip() for p in m.group(1).split("|")]
        if not parts:
            continue
        raw = parts[0].strip().lstrip("+")
        if raw:
            try:
                update["favour"] = int(raw)
            except ValueError:
                pass
        if len(parts) > 1 and parts[1]:
            update["attitude"] = parts[1]
        if len(parts) > 2 and parts[2]:
            update["relationship"] = parts[2]
    cleaned = _MARKER_STRIP.sub("", text).strip()
    return cleaned, (update or None)


def build_injection(state: dict) -> str:
    """拼出注入 system_prompt 的状态说明 + 更新指令。"""
    favour = int(state.get("favour", 0) or 0)
    name, desc = band(favour)
    # 低档位给「时机许可」：插件只负责什么时候可以冷、可以怼，
    # 具体说什么一律由人设决定（人格卡里已有自己的怼人口径）。
    if favour < -50:
        tip = (
            "到这个份上，你可以直接怼回去、也可以干脆不搭理：短句，带刺不带脏字，"
            "一两句收场，不追着吵。说什么，按你自己的人设来。\n"
        )
    elif favour < -10:
        tip = (
            "你对这人已经不太耐烦，可以冷淡、可以怼回去：短句，带笑不带脏字，"
            "一两句收场，不追着吵。说什么，按你自己的人设来。\n"
        )
    else:
        tip = ""
    return (
        "\n\n[内心状态 · 机密]\n"
        f"你对该用户当前的关系是：{state.get('relationship', '陌生人')}；"
        f"好感度：{favour}（-100 极度厌恶 ~ 100 挚爱）；"
        f"你对他的印象是：{state.get('attitude', '中立')}。\n"
        f"此刻你处于「{name}」区间，说话方式应是：{desc}。\n"
        f"{tip}"
        "在回复的最后另起一行，写出更新后的状态（用户看不到这一行）：\n"
        f"{MARKER} <好感度整数> | <印象> | <关系>\n"
        "规则：好感度写绝对值、不是增减量；正面互动 +1~+3，负面互动 -3~-10，"
        "提升要谨慎、下降要干脆；印象和关系各一句话，且必须与好感度一致；"
        "本轮无需改动就整行省略；不要用任何其他形式复述、暗示或解释这一行。"
    )


class FavourStore:
    """三维状态的读写。单文件 JSON，改动即落盘。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "favour.json")
        self.data: dict = self._load()

    # ---------- 存取 ----------
    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(f"[图恒宇] 读取好感度数据失败：{e}")
            return {}

    def _save(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"[图恒宇] 写入好感度数据失败：{e}")

    # ---------- 键 ----------
    @staticmethod
    def key(user_id: str, session_id: str | None = None) -> str:
        uid = str(user_id or "").strip()
        sid = str(session_id or "").strip()
        return f"{sid}_{uid}" if sid and uid else uid

    # ---------- 读写状态 ----------
    def get(self, user_id: str, session_id: str | None = None) -> dict:
        k = self.key(user_id, session_id)
        state = self.data.get(k)
        if not isinstance(state, dict):
            return dict(DEFAULT_STATE)
        out = dict(DEFAULT_STATE)
        out.update({kk: vv for kk, vv in state.items() if vv not in (None, "")})
        return out

    def update(self, user_id: str, patch: dict, session_id: str | None = None) -> dict:
        """把 patch 合并进当前状态后落盘。favour 会被夹到 -100~100。"""
        k = self.key(user_id, session_id)
        if not k:
            return dict(DEFAULT_STATE)
        state = self.get(user_id, session_id)
        for field in ("favour", "attitude", "relationship"):
            if field not in patch:
                continue
            val = patch[field]
            if field == "favour":
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    continue
                val = max(-100, min(100, val))
            else:
                val = str(val).strip()
                if not val:
                    continue
            state[field] = val
        self.data[k] = state
        self._save()
        return state

    def reset(self, user_id: str, session_id: str | None = None) -> None:
        k = self.key(user_id, session_id)
        if k in self.data:
            self.data[k] = dict(DEFAULT_STATE)
            self._save()
