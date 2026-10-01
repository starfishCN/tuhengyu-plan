"""作息：决定「此刻在干嘛」。

首次启动读人设 → 问模型生成一份一天作息 → 存盘。
之后直接读盘（不烧 token）。人设按指纹变了才重算。
空人设 / 生成失败 / 时间没命中 → 保守默认（活跃时段短、动作少）。

存放：data/plugin_data/astrbot_plugin_tuhengyu/schedule.json
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, time as dtime

logger = logging.getLogger("astrbot")

SCHEDULE_FILE = "schedule.json"

# 保守默认。宁可安静，也别顶着错的人设乱发东西。
CONSERVATIVE_PERIODS = [
    {"start": "09:00", "end": "23:00", "scene": "醒着", "state": "普通", "awake": True},
    {"start": "23:00", "end": "09:00", "scene": "睡着了", "state": "睡着", "awake": False},
]


@dataclass
class ScheduleState:
    """某一时刻的状态。"""

    awake: bool
    scene: str
    state: str
    source: str  # generated / manual / conservative

    def brief(self) -> str:
        return f"{'醒着' if self.awake else '睡着'} · {self.scene} · {self.state}"

    def now_line(self) -> str:
        """给内容生成用的一行「此刻」，让生成的东西贴得上现在的状态。"""
        return f"正在{self.scene}（心情：{self.state}）"


def parse_hhmm(s) -> dtime | None:
    try:
        return dtime.fromisoformat(str(s).strip()[:5])
    except (ValueError, TypeError, AttributeError):
        return None


def parse_periods(raw) -> list[dict]:
    """把模型输出 / 盘里的 periods 规整成合法结构。非法段直接丢。"""
    out = []
    if not isinstance(raw, list):
        return out
    for p in raw:
        if not isinstance(p, dict):
            continue
        a = parse_hhmm(p.get("start"))
        b = parse_hhmm(p.get("end"))
        if a is None or b is None:
            continue
        out.append({
            "start": a.strftime("%H:%M"),
            "end": b.strftime("%H:%M"),
            "scene": str(p.get("scene", "")).strip() or "在忙",
            "state": str(p.get("state", "")).strip() or "普通",
            "awake": bool(p.get("awake", True)),
        })
    return out


def extract_json(text: str) -> dict | None:
    """从模型输出里抠出 JSON 对象。容忍 ```json 包裹和前后废话。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        body = t[3:]
        if body.lower().startswith("json"):
            body = body[4:]
        t = body.split("```")[0] if "```" in body else body
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(t[i:j + 1])
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) else None


class Schedule:
    """作息表：生成一次、存盘、之后只读。"""

    def __init__(self, data_dir: str, config: dict):
        self.config = config or {}
        self.path = os.path.join(data_dir, SCHEDULE_FILE)
        self._periods: list[dict] = []
        self._source = "conservative"

    # ---------- 配置 ----------
    def _section(self) -> dict:
        v = self.config.get("schedule")
        return v if isinstance(v, dict) else {}

    def _persona(self) -> str:
        return str(self.config.get("persona_prompt", "")).strip()

    def _fingerprint(self) -> str:
        raw = self._persona()
        if not raw:
            return ""
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    # ---------- 盘 ----------
    def _load(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"[图恒宇] 作息文件读取失败：{e}")
            return None

    def _save(self, periods: list[dict], source: str) -> None:
        data = {
            "fingerprint": self._fingerprint(),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "periods": periods,
        }
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning(f"[图恒宇] 作息文件写入失败：{e}")

    # ---------- 对外 ----------
    async def ensure(self, context) -> None:
        """保证有一份可用作息。初始化时调一次，之后 tick 只读。"""
        sec = self._section()
        manual = str(sec.get("manual_hours", "")).strip()

        if not sec.get("auto_generate", True):
            self._periods = self._from_hours(manual)
            self._source = "manual"
            logger.info(f"[图恒宇] 作息：手填（{manual or '默认'}）")
            return

        cached = self._load()
        if cached and cached.get("fingerprint") == self._fingerprint():
            periods = parse_periods(cached.get("periods"))
            if periods:
                self._periods = periods
                self._source = "generated"
                logger.info(f"[图恒宇] 作息：读盘（{len(periods)} 段）")
                return

        if not self._persona():
            self._fallback("人设为空")
            return

        periods = await self._generate(context)
        if periods:
            self._periods = periods
            self._source = "generated"
            self._save(periods, "generated")
            logger.info(f"[图恒宇] 作息：已生成并存盘（{len(periods)} 段）")
        else:
            self._fallback("生成失败")

    def _fallback(self, reason: str) -> None:
        logger.warning(f"[图恒宇] 作息：{reason}，用保守默认。")
        self._periods = [dict(p) for p in CONSERVATIVE_PERIODS]
        self._source = "conservative"

    def _from_hours(self, spec: str) -> list[dict]:
        """把 09:00-23:00 这类写法转成 periods（醒/睡两段）。"""
        out = []
        for part in (spec or "09:00-23:00").split(","):
            part = part.strip()
            if "-" not in part:
                continue
            a, b = part.split("-", 1)
            if parse_hhmm(a) and parse_hhmm(b):
                out.append({
                    "start": a.strip()[:5], "end": b.strip()[:5],
                    "scene": "醒着", "state": "普通", "awake": True,
                })
        if not out:
            return [dict(p) for p in CONSERVATIVE_PERIODS]
        out.append({
            "start": out[0]["end"], "end": out[0]["start"],
            "scene": "睡着了", "state": "睡着", "awake": False,
        })
        return out

    async def _generate(self, context) -> list[dict]:
        from .llm import generate_schedule_text

        text = await generate_schedule_text(
            context,
            self._persona(),
            str(self._section().get("generate_model", "")).strip(),
        )
        data = extract_json(text)
        if not data:
            return []
        return parse_periods(data.get("periods"))

    def state_at(self, now: datetime | None = None) -> ScheduleState:
        """此刻的状态。没命中任何时段 → 保守（睡着）。"""
        now = now or datetime.now()
        t = now.time()
        for p in self._periods or CONSERVATIVE_PERIODS:
            a = parse_hhmm(p.get("start"))
            b = parse_hhmm(p.get("end"))
            if a is None or b is None:
                continue
            hit = (a <= t <= b) if a <= b else (t >= a or t <= b)
            if hit:
                return ScheduleState(
                    awake=bool(p.get("awake", True)),
                    scene=str(p.get("scene", "")),
                    state=str(p.get("state", "")),
                    source=self._source,
                )
        return ScheduleState(awake=False, scene="没安排", state="安静", source=self._source)

    def describe(self) -> str:
        """给 /图恒宇 命令用的一行摘要。"""
        return f"{self._source} · {len(self._periods or CONSERVATIVE_PERIODS)} 段"