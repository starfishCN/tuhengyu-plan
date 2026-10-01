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
from astrbot.api.web import error_response, json_response

from .core.persona import resolve_persona
from .core.scheduler import LifeScheduler

# Web API 路由必须以插件名为前缀（AstrBot 约定，2026-10-01 核对官方文档）。
PLUGIN_NAME = "astrbot_plugin_tuhengyu"


class TuhengyuPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.config = config or {}
        self._scheduler = None
        self._task = None
        # 注册插件页面的后端 API（页面在 pages/status/）。
        try:
            context.register_web_api(
                f"/{PLUGIN_NAME}/status",
                self.page_status,
                ["GET"],
                "插件页面：运行状态",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/reschedule",
                self.page_reschedule,
                ["POST"],
                "插件页面：重算作息",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/test-moment",
                self.page_test_moment,
                ["POST"],
                "插件页面：立即发一条空间动态",
            )
        except Exception as e:  # 注册失败不影响主体功能
            self.logger.warning(f"[图恒宇] 注册页面 API 失败：{e}")

    # ---------- 生命周期 ----------
    async def initialize(self):
        """插件加载后调用：启动生活调度器。"""
        if not self.config.get("enabled", True):
            self.logger.info("[图恒宇] 插件已禁用，不启动调度器。")
            return
        self._scheduler = LifeScheduler(self.context, self.config, self._data_dir())
        await self._refresh_persona()  # 先解析人设，作息生成依赖它
        await self._scheduler.setup()  # 生成 / 读取作息（失败会兜底，不抛）
        self._task = asyncio.create_task(self._scheduler.run(), name="tuhengyu_scheduler")
        self.logger.info("[图恒宇] 生活调度器已启动。")

    async def _refresh_persona(self) -> None:
        """重新从 AstrBot 解析当前人设并下发给调度器 / 作息。

        每次对外查询前都跑一遍：这样博士在 AstrBot 里换了人格，插件立刻跟上，
        不必重启插件、也不必再往插件里抄一份人设。
        """
        if self._scheduler is None:
            return
        try:
            text, label, name = await resolve_persona(self.context, self.config)
        except Exception as e:  # 解析失败不致命，退回原值
            self.logger.warning(f"[图恒宇] 解析人设失败：{e}")
            return
        self._scheduler.set_persona(text, label, name)

    def _data_dir(self) -> str:
        """插件数据目录：data/plugin_data/astrbot_plugin_tuhengyu。"""
        import os

        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

            return os.path.join(get_astrbot_plugin_data_path(), "astrbot_plugin_tuhengyu")
        except Exception as e:  # API 变动时不致命，退到插件目录旁
            self.logger.warning(f"[图恒宇] 取数据目录失败，退回插件目录：{e}")
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    async def terminate(self):
        """插件卸载时调用：停调度器。"""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.logger.info("[图恒宇] 生活调度器已停止。")

    # ---------- 命令 ----------
    async def _publish_once(self) -> dict:
        """生成并发布一条空间动态。命令与插件页面共用同一条路径。"""
        if self._scheduler is None:
            return {"ok": False, "message": "调度器未运行（插件可能被禁用）。"}
        await self._refresh_persona()
        from .core.llm import generate_moment_text

        st = self._scheduler.schedule.state_at()
        content = await generate_moment_text(self.context, self.config, st.now_line())
        if not content:
            return {"ok": False, "message": "内容生成失败：没有可用模型，看日志。", "state": st.brief()}
        ok = await self._scheduler._post_moment(content)
        if ok:
            self._scheduler._last_moment = datetime.now()
            return {"ok": True, "message": "已发布", "content": content, "state": st.brief()}
        return {
            "ok": False,
            "message": "发布失败，看 AstrBot 日志里的 [图恒宇] 行。",
            "content": content,
            "state": st.brief(),
        }

    @filter.command("图恒宇")
    async def status(self, event: AstrMessageEvent):
        """查看插件状态。"""
        if self._scheduler is None:
            yield event.plain_result("[图恒宇] 调度器未运行（插件可能被禁用）。")
            return
        await self._refresh_persona()
        yield event.plain_result(self._scheduler.status_text())

    @filter.command("图恒宇测试")
    async def test_moment(self, event: AstrMessageEvent):
        """立刻手动发一条空间动态，用于验证链路是否打通。"""
        if self._scheduler is None:
            yield event.plain_result("[图恒宇] 调度器未运行。")
            return
        yield event.plain_result("[图恒宇] 正在生成并发布，稍等 ...")
        try:
            r = await self._publish_once()
            if r.get("ok"):
                yield event.plain_result(f"[图恒宇] 已发布（此刻：{r.get('state')}）：{r.get('content')}")
            elif r.get("content"):
                yield event.plain_result("[图恒宇] 发布失败，看 AstrBot 日志里的 [图恒宇] 行。")
            else:
                yield event.plain_result(f"[图恒宇] {r.get('message')}")
        except Exception as e:
            yield event.plain_result(f"[图恒宇] 出错：{e}")

    # ---------- 插件页面 API ----------
    async def page_status(self):
        """GET /astrbot_plugin_tuhengyu/status —— 结构化运行状态。"""
        if self._scheduler is None:
            return json_response({"running": False})
        await self._refresh_persona()
        data = self._scheduler.status_dict()
        data["running"] = True
        return json_response(data)

    async def page_reschedule(self):
        """POST /astrbot_plugin_tuhengyu/reschedule —— 丢弃旧作息并重新生成。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        await self._refresh_persona()  # 先取当前人设，再按它重算
        try:
            await self._scheduler.schedule.regenerate(self.context)
        except Exception as e:
            return error_response(f"重算失败：{e}", status_code=500)
        data = self._scheduler.status_dict()
        data["running"] = True
        return json_response(data)

    async def page_test_moment(self):
        """POST /astrbot_plugin_tuhengyu/test-moment —— 立即发一条（等同 /图恒宇测试）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            result = await self._publish_once()
        except Exception as e:
            return error_response(f"发布出错：{e}", status_code=500)
        data = self._scheduler.status_dict()
        data["running"] = True
        data["result"] = result
        return json_response(data)