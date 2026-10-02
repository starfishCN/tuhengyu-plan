"""命令：状态、测试发空间、好感度、token 诊断。"""

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


class CommandHandlers:

    # ---------- 命令 ----------
    async def _publish_once(self) -> dict:
        """生成并发布一条空间动态。命令与插件页面共用同一条路径。"""
        if self._scheduler is None:
            return {"ok": False, "message": "调度器未运行（插件可能被禁用）。"}
        await self._refresh_persona()
        from .core.llm import generate_moment_text

        st = self._scheduler.schedule.state_at()
        # 关键：把当前人设传进去。不传就会退回通用口吻 → 说说不带人设（老问题）。
        content = await generate_moment_text(
            self.context, self.config, st.now_line(), self._scheduler.persona_text
        )
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

    @filter.command("图恒宇好感")
    async def favour_status(self, event: AstrMessageEvent):
        """查看自己当前的好感度 / 印象 / 关系（只读）。"""
        sec = self._favour_cfg()
        if not sec.get("enabled", True):
            yield event.plain_result("[图恒宇] 好感度系统未启用。")
            return
        uid = str(event.get_sender_id() or "")
        state = self._favour().get(uid, self._scope(event, sec))
        yield event.plain_result(
            f"[图恒宇] 好感度 {state['favour']}｜印象：{state['attitude']}"
            f"｜关系：{state['relationship']}"
        )

    @filter.command("token诊断")
    async def token_diag(self, event: AstrMessageEvent):
        """查看上一次 LLM 请求的 token 构成，以及今日累计用量。"""
        d = self._tok_last
        if not d:
            yield event.plain_result("[图恒宇] token 诊断：本次运行还没捕获到 LLM 请求。")
            return
        sys_t = self._est_tokens(d.get("sys_chars", 0))
        ctx_t = self._est_tokens(d.get("ctx_chars", 0))
        tool_t = self._est_tokens(d.get("tools_chars", 0))
        total = sys_t + ctx_t + tool_t + self._est_tokens(d.get("prompt_chars", 0))
        st = self._tok_stats
        lines = [
            f"[图恒宇] token 诊断（最近一次请求 {d.get('at')}，模型 {d.get('model')}）",
            f"system_prompt：{d.get('sys_chars', 0)} 字符 ≈ {sys_t} token",
            f"上下文：{d.get('ctx_count', 0)} 条 / {d.get('ctx_chars', 0)} 字符 ≈ {ctx_t} token",
            f"工具：{len(d.get('tools') or [])} 个 / {d.get('tools_chars', 0)} 字符 ≈ {tool_t} token",
            f"本次合计 ≈ {total} token",
            f"今日：私聊 {st.get('p_reqs', 0)} 次，输入 ≈ {st.get('p_in', 0)} token",
            f"　　　全部 {st.get('reqs', 0)} 次，输出 ≈ {st.get('out', 0)} token",
        ]
        tools = d.get("tools") or []
        if tools:
            top = "、".join(f"{n}≈{self._est_tokens(c)}" for n, c in tools[:6])
            lines.append(f"工具明细（前 6）：{top}")
        yield event.plain_result("\n".join(lines))
