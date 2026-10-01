"""图恒宇计划 —— 拟人化生活插件

给 bot「完整的一生」：它有自己的作息，会自己发空间。

第一版范围：作息 + 调度器 + 发空间。
    调度器按「活跃时段 + 检查间隔 + 触发概率」决定何时行动；
    每次行动时先用 AstrBot 的模型生成内容，再发到 QQ 空间。

适配 AstrBot v4（API 依据：/AstrBot/astrbot/core/star/ 源码，2026-10-01 核对）。
    - 插件类继承 star.Star，元信息写在 metadata.yaml（@register 装饰器已废弃）
    - 实例方法 async def initialize(self) / async def terminate(self)
    - 平台访问：context.get_platform("aiocqhttp") → platform.get_client() → bot.call_action()
"""
import asyncio
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

from .core.scheduler import LifeScheduler


class TuhengyuPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.config = config or {}
        self._scheduler = None
        self._task = None

    # ---------- 生命周期 ----------
    async def initialize(self):
        """插件加载后调用：启动生活调度器。"""
        if not self.config.get("enabled", True):
            self.logger.info("[图恒宇] 插件已禁用，不启动调度器。")
            return
        self._scheduler = LifeScheduler(self.context, self.config)
        self._task = asyncio.create_task(self._scheduler.run(), name="tuhengyu_scheduler")
        self.logger.info("[图恒宇] 生活调度器已启动。")

    async def terminate(self):
        """插件卸载时调用：停调度器。"""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.logger.info("[图恒宇] 生活调度器已停止。")

    # ---------- 命令 ----------
    @filter.command("图恒宇")
    async def status(self, event: AstrMessageEvent):
        """查看插件状态。"""
        if self._scheduler is None:
            yield event.plain_result("[图恒宇] 调度器未运行（插件可能被禁用）。")
            return
        cfg = self.config
        yield event.plain_result(
            "[图恒宇] 调度器运行中。\n"
            f"活跃时段：{cfg.get('active_hours', '09:00-23:00')}\n"
            f"检查间隔：{cfg.get('check_interval_minutes', 30)} 分钟\n"
            f"触发概率：{cfg.get('act_probability', 0.15)}\n"
            f"发空间：{'开' if cfg.get('moment_enabled', True) else '关'}"
            f"（最短间隔 {cfg.get('moment_min_interval_hours', 6)} 小时）\n"
            f"上次发空间：{self._scheduler._last_moment or '无'}"
        )

    @filter.command("图恒宇测试")
    async def test_moment(self, event: AstrMessageEvent):
        """立刻手动发一条空间动态，用于验证链路是否打通。"""
        if self._scheduler is None:
            yield event.plain_result("[图恒宇] 调度器未运行。")
            return
        yield event.plain_result("[图恒宇] 正在生成并发布，稍等 ...")
        try:
            from .core.llm import generate_moment_text

            content = await generate_moment_text(self.context, self.config)
            if not content:
                yield event.plain_result("[图恒宇] 内容生成失败：没有可用模型，看日志。")
                return
            ok = await self._scheduler._post_moment(content)
            if ok:
                self._scheduler._last_moment = datetime.now()
                yield event.plain_result(f"[图恒宇] 已发布：{content}")
            else:
                yield event.plain_result("[图恒宇] 发布失败，看 AstrBot 日志里的 [图恒宇] 行。")
        except Exception as e:
            yield event.plain_result(f"[图恒宇] 出错：{e}")