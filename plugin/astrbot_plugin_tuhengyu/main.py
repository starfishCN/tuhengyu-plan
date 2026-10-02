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
import json
import os
import random
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Image, Poke
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request as web_request

from .core.classify import classify_image
from .core.favour import FavourStore, build_injection, parse_state_marker
from .core.intent import FALLBACK as INTENT_FALLBACK
from .core.intent import labels as intent_labels
from .core.persona import resolve_persona
from .core.proactive import build_proactive_prompt, decide_proactive
from .core.poke import IGNORE as POKE_IGNORE
from .core.poke import build_poke_prompt, decide as decide_poke, fallback_text
from .core.scheduler import LifeScheduler
from .core.stickers import SYSTEM_LABELS, read_base64, save_collected, thumb_b64

# Web API 路由必须以插件名为前缀（AstrBot 约定，2026-10-01 核对官方文档）。
PLUGIN_NAME = "astrbot_plugin_tuhengyu"


# 职责已按模块拆出；本文件只保留生命周期、公共辅助与注册。
from .handlers.sticker import StickerHandlers
from .handlers.favour import FavourHandlers
from .handlers.poke import PokeHandlers
from .handlers.proactive import ProactiveHandlers
from .diag.token import TokenHandlers
from .commands import CommandHandlers
from .web.routes import WebRoutes
from .web.settings import SettingsHandlers

class TuhengyuPlugin(StickerHandlers, FavourHandlers, PokeHandlers, ProactiveHandlers, TokenHandlers, CommandHandlers, WebRoutes, SettingsHandlers, Star):

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.config = config or {}
        self._scheduler = None
        self._task = None
        self._favour_store = None
        self._poke_log = {}  # 戳一戳：键 → [时间戳]，用于连戳计数与冷却
        self._bridge_obj = None  # OneBot 桥（回戳用 send_poke 动作）
        self._tok_last = None  # 最近一次 LLM 请求的构成快照（token 诊断用）
        self._tok_stats = self._tok_load()  # 今日请求 / token 累计（存盘）
        self._groups = {}  # 群聊观察：gid → {msgs, last_spoke, day, count}
        self._proactive_load()  # 读回每群的冷却 / 今日计数
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
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-reload",
                self.page_sticker_reload,
                ["POST"],
                "插件页面：重扫表情包目录",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/stickers",
                self.page_stickers,
                ["GET"],
                "插件页面：表情包库（按意图分组）",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-category",
                self.page_sticker_category,
                ["POST"],
                "插件页面：新建表情包分类",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-upload",
                self.page_sticker_upload,
                ["POST"],
                "插件页面：上传表情包",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-classify",
                self.page_sticker_classify,
                ["POST"],
                "插件页面：识图自动归类",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/sticker-move",
                self.page_sticker_move,
                ["POST"],
                "插件页面：手动移动表情包分类",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/settings",
                self.page_settings_get,
                ["GET"],
                "插件页面：读取设置",
            )
            context.register_web_api(
                f"/{PLUGIN_NAME}/settings",
                self.page_settings_post,
                ["POST"],
                "插件页面：保存设置",
            )
        except Exception as e:  # 注册失败不影响主体功能
            self.logger.warning(f"[图恒宇] 注册页面 API 失败：{e}")

    # ---------- 生命周期 ----------
    def _bind_submodule_handlers(self) -> None:
        """把本包下子模块注册的 handler 归到主模块，并绑定到本插件实例。

        AstrBot 有两处按 handler.handler_module_path（其值是该函数定义所在的模块）：
          1) star_map 精确查找判定 handler 属于哪个插件 —— 查不到即当作「未激活插件」
             在唤醒阶段整体跳过（core/star/star_handler.py 的 only_activated 检查）；
          2) 加载时只对 module_path == 插件主模块的 handler 做实例绑定
             （core/star/star_manager.py 的 rebind 段，functools.partial(raw, star_cls)）。
        本插件的 handler 定义在 commands / handlers.* 等子模块里，module_path 与主模块
        不同，于是既被判为未激活、又没被绑定实例，调用时报缺 self / 缺 event ——
        命令、表情包、戳一戳、群聊观察、好感注入会一起失效。

        这里做两件事：把子模块路径别名到主模块元数据（补查找），以及把这些 handler 的
        module_path 归一到主模块并用 functools.partial 绑到本实例（补绑定）。每轮加载都
        跑一遍，可重复执行。
        """
        try:
            import functools
            import sys as _sys

            from astrbot.core.star.star import star_map as _star_map
            from astrbot.core.star.star_handler import (
                star_handlers_registry as _reg,
            )
        except Exception as e:  # API 变动时不致命
            self.logger.warning(f"[图恒宇] 绑定子模块 handler 失败：{e}")
            return
        me = _star_map.get(__name__)
        if me is None:
            return
        pkg = __package__ or __name__.rsplit(".", 1)[0]
        # 1) 子模块路径 → 主模块元数据，供 star_map 查找
        for mod_name in list(_sys.modules):
            if mod_name.startswith(pkg + ".") and mod_name != __name__:
                _star_map[mod_name] = me
        # 2) 子模块 handler：归一到主模块并绑定本实例
        for h in list(_reg):
            mp = getattr(h, "handler_module_path", None)
            if not mp or mp == __name__ or not mp.startswith(pkg + "."):
                continue
            raw = (
                h.handler.func
                if isinstance(h.handler, functools.partial)
                else h.handler
            )
            h.handler = functools.partial(raw, self)
            h.handler_module_path = __name__

    async def initialize(self):
        """插件加载后调用：启动生活调度器。"""
        self._bind_submodule_handlers()  # 必须先做：否则本插件 handler 全被跳过
        if not self.config.get("enabled", True):
            self.logger.info("[图恒宇] 插件已禁用，不启动调度器。")
            return
        self._scheduler = LifeScheduler(self.context, self.config, self._data_dir())
        await self._refresh_persona()  # 先解析人设，作息生成依赖它
        await self._scheduler.setup()  # 生成 / 读取作息（失败会兜底，不抛）
        self._scheduler.add_action(self._maybe_proactive)  # 主动插话挂到调度器
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
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

            return os.path.join(get_astrbot_plugin_data_path(), "astrbot_plugin_tuhengyu")
        except Exception as e:  # API 变动时不致命，退到插件目录旁
            self.logger.warning(f"[图恒宇] 取数据目录失败，退回插件目录：{e}")
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    def _data_file(self, name: str) -> str:
        """数据目录下的一个文件路径。"""
        return os.path.join(self._data_dir(), name)

    def _sec(self, name: str) -> dict:
        """取某个配置分组，保证返回 dict（缺失 / 类型不对时给空 dict）。"""
        sec = self.config.get(name) if isinstance(self.config, dict) else None
        return sec if isinstance(sec, dict) else {}

    async def terminate(self):
        """插件卸载时调用：停调度器。"""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.logger.info("[图恒宇] 生活调度器已停止。")
