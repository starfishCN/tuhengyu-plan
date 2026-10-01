"""生活调度器：决定「什么时候该有行动」。

第一版只做一条流水线：检查作息 → 掷骰子 → 发空间。
后续行动（表情包 / 主动发言 / 怼人时机）都挂到 _act() 上。
"""
import asyncio
import logging
import random
from datetime import datetime, time as dtime

from .llm import generate_moment_text
from .onebot import OneBotBridge
from .qzone import QzoneClient

logger = logging.getLogger("astrbot")


class LifeScheduler:
    def __init__(self, context, config):
        self.context = context
        self.config = config
        self._last_moment = None  # datetime of last posted moment
        self.bridge = OneBotBridge(context)
        self._qzone = QzoneClient(self.bridge)

    # ---------- 作息 ----------
    def in_active_hours(self, now: datetime) -> bool:
        spec = str(self.config.get("active_hours", "09:00-23:00"))
        t = now.time()
        for part in spec.split(","):
            part = part.strip()
            if "-" not in part:
                continue
            a, b = part.split("-", 1)
            try:
                start = dtime.fromisoformat(a.strip()[:5])
                end = dtime.fromisoformat(b.strip()[:5])
            except ValueError:
                continue
            if start <= end:
                if start <= t <= end:
                    return True
            else:  # 跨午夜
                if t >= start or t <= end:
                    return True
        return False

    # ---------- 主循环 ----------
    async def run(self):
        interval = max(1, int(self.config.get("check_interval_minutes", 30))) * 60
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
        if not self.in_active_hours(now):
            return
        if random.random() > float(self.config.get("act_probability", 0.15)):
            return
        await self.act(now)

    async def act(self, now: datetime):
        # 第一版只有「发空间」一种行动，后续在此扩展
        await self.maybe_moment(now)

    # ---------- 行动：发空间 ----------
    async def maybe_moment(self, now: datetime):
        if not self.config.get("moment_enabled", True):
            return
        min_gap = float(self.config.get("moment_min_interval_hours", 6)) * 3600
        if self._last_moment and (now - self._last_moment).total_seconds() < min_gap:
            return

        # 接口已于 2026-10-01 实测确认：OneBot v11 与协议端均无「发空间」动作，
        # 走直连 QQ 空间 Web 接口（带 cookie，逆向、可能随官方改动失效）。
        # 实现见 core/qzone.py。
        content = await generate_moment_text(self.context, self.config)
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
