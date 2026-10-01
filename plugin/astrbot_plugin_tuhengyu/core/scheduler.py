"""生活调度器：决定「什么时候该有行动」。

一条流水线：看作息 → 醒着吗 → 按状态加权掷骰 → 行动。
作息由 core/schedule.py 提供（跟人设走，生成一次存盘，之后只读）。

第一版只有一种行动：发 QQ 空间。
后续行动（表情包 / 主动发言 / 怼人时机）都挂到 act() 上。

「接日程」指两件事：
    1. 行动的内容带上「此刻在干嘛」——生成时把 scene / state 喂给模型；
    2. 行动的时机按状态加权——在忙 / 累就少动，闲 / 放松才多动。
"""
import asyncio
import logging
import random
from datetime import datetime

from .llm import generate_moment_text
from .onebot import OneBotBridge
from .qzone import QzoneClient
from .schedule import Schedule

logger = logging.getLogger("astrbot")

# 状态→概率倍数。命中关键词即取该值，都不命中为 1.0。
# 关键词写在 scene / state 里（模型生成时是自由文本，只能模糊匹配）。
STATE_BIAS = [
    (0.35, ("忙", "工作", "上班", "上课", "学习", "考试", "开会", "加班", "赶", "通勤", "车里")),
    (1.60, ("闲", "空", "休息", "放松", "发呆", "散步", "咖啡", "茶", "听歌", "躺", "阳台", "夜")),
]
BIAS_MIN, BIAS_MAX = 0.35, 1.60
PROB_CAP = 0.90


def _section(config, name: str) -> dict:
    """安全取嵌套配置段。schema 里的 object 存成嵌套 dict。"""
    v = config.get(name) if isinstance(config, dict) else None
    return v if isinstance(v, dict) else {}


def state_bias(st) -> float:
    """按当前状态给触发概率一个倍数。没状态信息就 1.0。"""
    if st is None:
        return 1.0
    text = f"{getattr(st, 'scene', '')}{getattr(st, 'state', '')}"
    for factor, words in STATE_BIAS:
        if any(w in text for w in words):
            return factor
    return 1.0


class LifeScheduler:
    def __init__(self, context, config, data_dir: str):
        self.context = context
        self.config = config or {}
        self.schedule = Schedule(data_dir, self.config)
        self._last_moment = None  # datetime of last posted moment
        self.bridge = OneBotBridge(context)
        self._qzone = QzoneClient(self.bridge)

    # ---------- 启动 ----------
    async def setup(self) -> None:
        """初始化作息。内部已有兜底，失败不抛。"""
        await self.schedule.ensure(self.context)

    # ---------- 主循环 ----------
    async def run(self):
        interval = max(
            1, int(_section(self.config, "scheduler").get("check_interval_minutes", 30))
        ) * 60
        while True:
            try:
                await asyncio.sleep(interval)
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:  # 单次异常不打断整个循环
                logger.warning(f"[图恒宇] 调度循环异常：{e}")

    async def tick(self):
        now = datetime.now()
        st = self.schedule.state_at(now)
        if not st.awake:
            return
        await self.act(now, st)

    async def act(self, now: datetime, st=None):
        """决定并执行一次行动。

        门槛与掷骰都放在这里（原来在 tick 里），因为不同行动将来
        会有各自的适用条件和冷却，得逐条判。
        """
        if st is not None and not getattr(st, "awake", True):
            return

        prob = float(_section(self.config, "scheduler").get("act_probability", 0.15))
        factor = state_bias(st) if _section(self.config, "scheduler").get("state_bias", True) else 1.0
        prob = min(PROB_CAP, max(0.0, prob * factor))
        if random.random() > prob:
            return
        logger.info(f"[图恒宇] 触发行动：{st.brief() if st else '无状态'}，概率 {prob:.2f}")

        # 第一版只有「发空间」一种行动，后续在此扩展。
        await self.maybe_moment(now, st)

    # ---------- 行动：发空间 ----------
    async def maybe_moment(self, now: datetime, st=None):
        moment = _section(self.config, "moment")
        if not moment.get("enabled", True):
            return
        min_gap = float(moment.get("min_interval_hours", 6)) * 3600
        if self._last_moment and (now - self._last_moment).total_seconds() < min_gap:
            return

        # 接口已于 2026-10-01 实测确认：OneBot v11 与协议端均无「发空间」动作，
        # 走直连 QQ 空间 Web 接口（带 cookie，逆向、可能随官方改动失效）。
        # 实现见 core/qzone.py。
        state_line = st.now_line() if st is not None else ""
        content = await generate_moment_text(self.context, self.config, state_line)
        if content:
            ok = await self._post_moment(content)
            if ok:
                self._last_moment = now
                logger.info(f"[图恒宇] 已发空间：{content[:30]}")

    async def _post_moment(self, content: str) -> bool:
        """真正把动态发出去。

        实现路径（2026-10-01 在真实环境实测通过）：
            OneBot get_cookies(domain=空间域) → p_skey → bkn() → g_tk
            → POST emotion_cgi_publish_v6 → code:0 即成功
        细节见 core/qzone.py。
        """
        if self._qzone is None:
            logger.warning("[图恒宇] QzoneClient 未初始化。")
            return False
        return await self._qzone.publish(content)

    # ---------- 对外：状态文本 ----------
    def status_text(self) -> str:
        """给 /图恒宇 命令用。"""
        now = datetime.now()
        st = self.schedule.state_at(now)
        sch = _section(self.config, "scheduler")
        moment = _section(self.config, "moment")
        base = float(sch.get("act_probability", 0.15))
        if sch.get("state_bias", True):
            factor = state_bias(st)
            eff = min(PROB_CAP, max(0.0, base * factor))
            prob_line = f"触发概率：{base} × 状态 {factor} → {eff:.2f}"
        else:
            prob_line = f"触发概率：{base}（状态加权已关）"
        lines = [
            "[图恒宇] 调度器运行中。",
            f"此刻：{st.brief()}　（作息来源：{st.source}，{self.schedule.describe()}）",
            f"检查间隔：{sch.get('check_interval_minutes', 30)} 分钟",
            prob_line,
            (
                f"发空间：{'开' if moment.get('enabled', True) else '关'}"
                f"（最短间隔 {moment.get('min_interval_hours', 6)} 小时）"
            ),
            f"上次发空间：{self._last_moment or '无'}",
        ]
        return "\n".join(lines)