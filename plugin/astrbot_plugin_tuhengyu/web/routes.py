"""Web API 路由（必须以插件名为前缀）。"""

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
from ..core.classify import classify_image
from ..core.favour import (
    FavourStore,
    build_injection,
    parse_curve_json,
    parse_state_marker,
    persona_fingerprint,
)
from ..core.intent import FALLBACK as INTENT_FALLBACK
from ..core.intent import labels as intent_labels
from ..core.llm import generate_curve_text
from ..core.persona import resolve_persona
from ..core.proactive import build_proactive_prompt, decide_proactive
from ..core.poke import IGNORE as POKE_IGNORE
from ..core.poke import build_poke_prompt, decide as decide_poke, fallback_text
from ..core.scheduler import LifeScheduler
from ..core.stickers import SYSTEM_LABELS, read_base64, save_collected, thumb_b64


class WebRoutes:

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

    async def page_moment_publish(self):
        """POST /astrbot_plugin_tuhengyu/moment-publish —— 直接发一条自定义内容（不经模型）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            body = await web_request.json({})
        except Exception as e:
            return error_response(f"读取请求体失败：{e}", status_code=400)
        content = str((body or {}).get("content", "")).strip()
        if not content:
            return error_response("内容为空。", status_code=400)
        if len(content) > 1000:
            return error_response("内容过长（上限 1000 字）。", status_code=400)
        try:
            ok = await self._scheduler._post_moment(content)
        except Exception as e:
            return error_response(f"发布出错：{e}", status_code=500)
        if ok:
            self._scheduler._last_moment = datetime.now()
        data = self._scheduler.status_dict()
        data["running"] = True
        data["result"] = {
            "ok": bool(ok),
            "content": content,
            "message": "已发布" if ok else "发布失败，看 AstrBot 日志里的 [图恒宇] 行。",
        }
        return json_response(data)

    async def page_moment_recent(self):
        """GET /astrbot_plugin_tuhengyu/moment-recent —— 回读最近几条说说（验证用）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        client = getattr(self._scheduler, "_qzone", None)
        if client is None:
            return json_response(
                {"ok": False, "auth": False, "items": [], "message": "空间客户端未初始化。"}
            )
        try:
            auth = await client.auth()
        except Exception as e:
            return json_response(
                {"ok": False, "auth": False, "items": [], "message": f"鉴权失败：{e}"}
            )
        if auth is None:
            return json_response(
                {
                    "ok": False,
                    "auth": False,
                    "items": [],
                    "message": "拿不到空间 cookie（协议端未连接，或登录态失效）。",
                }
            )
        try:
            raw = await client.recent(3)
        except Exception as e:
            return json_response(
                {"ok": False, "auth": True, "items": [], "message": f"读取失败：{e}"}
            )
        items = []
        for it in raw or []:
            try:
                node = it or {}
                content = str(node.get("content") or "").strip()
                ts = node.get("created_time") or node.get("created") or 0
                when = (
                    datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M") if ts else ""
                )
                items.append({"time": when, "content": content})
            except Exception:
                continue
        return json_response({"ok": True, "auth": True, "uin": auth.uin, "items": items})

    async def page_sticker_reload(self):
        """POST /astrbot_plugin_tuhengyu/sticker-reload —— 重扫表情包目录。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            self._scheduler.stickers.reload()
        except Exception as e:
            return error_response(f"重扫失败：{e}", status_code=500)
        data = self._scheduler.status_dict()
        data["running"] = True
        return json_response(data)

    async def page_stickers(self):
        """GET /astrbot_plugin_tuhengyu/stickers —— 表情包库按标签分组（含 base64 预览）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        lib = self._scheduler.stickers
        try:
            groups = lib.groups_by_intent()
        except Exception as e:
            return error_response(f"读取表情包失败：{e}", status_code=500)

        max_item = 800 * 1024  # 原图直接内联的上限（缩略不可用时的回退）
        max_total = 24 * 1024 * 1024  # 内联总量上限
        max_src = 20 * 1024 * 1024  # 超过此大小的原图不尝试生成缩略
        total = 0
        truncated = False
        out = []
        for label, items in groups.items():
            pairs = sorted(items, key=lambda tp: tp[1].name)
            images = []
            for tag, p in pairs:
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                item = {"name": p.name, "size": size, "tag": tag}
                if total >= max_total:
                    item["skipped"] = True
                    truncated = True
                    images.append(item)
                    continue
                # ① 优先缩略图（大多数图都能看，且响应小）
                thumb = thumb_b64(p) if size <= max_src else None
                if thumb:
                    b64, w, h = thumb
                    item["b64"] = b64
                    item["thumb"] = True
                    item["w"] = w
                    item["h"] = h
                    total += int(len(b64) * 0.75)
                    images.append(item)
                    continue
                # ② 回退：小图直接内联原图
                if size <= max_item:
                    raw = read_base64(p)
                    if raw:
                        item["b64"] = raw
                        total += size
                    else:
                        item["error"] = "读取失败"
                else:
                    item["skipped"] = True
                    truncated = True
                images.append(item)
            out.append(
                {
                    "label": label,
                    "count": len(pairs),
                    "images": images,
                    # 拖拽落点：内置意图 / 用户分类 = 同名目录；「其他」= default 散图区
                    "drop": "default" if label == INTENT_FALLBACK else label,
                }
            )

        return json_response(
            {
                "groups": out,
                "categories": lib.categories(),
                "desc": lib.describe(),
                "total_bytes": total,
                "truncated": truncated,
                "max_item": max_item,
            }
        )

    async def page_sticker_category(self):
        """POST /astrbot_plugin_tuhengyu/sticker-category —— 新建一个表情包分类（子目录）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        name = str((body or {}).get("name", "")).strip()
        ok, msg = self._scheduler.stickers.add_category(name)
        if not ok:
            return error_response(msg, status_code=400)
        data = self._scheduler.status_dict()
        data["running"] = True
        data["message"] = msg
        return json_response(data)

    async def page_sticker_upload(self):
        """POST /astrbot_plugin_tuhengyu/sticker-upload —— 上传一张图到指定分类（base64）。"""
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        import base64

        category = str((body or {}).get("category", "")).strip()
        filename = str((body or {}).get("filename", "")).strip()
        raw = (body or {}).get("data", "")
        try:
            data_bytes = base64.b64decode(raw) if raw else b""
        except Exception:
            data_bytes = b""
        ok, msg = self._scheduler.stickers.save_image(category, filename, data_bytes)
        if not ok:
            return error_response(msg, status_code=400)
        out = self._scheduler.status_dict()
        out["running"] = True
        out["message"] = msg
        return json_response(out)

    async def page_sticker_classify(self):
        """POST /astrbot_plugin_tuhengyu/sticker-classify —— 识图把散图归入意图类目。

        对 default / collected 下的图逐张调一次多模态模型（消耗 token，只在这里发生）。
        用户自建分类名也作为候选类目参与判定；判为「其他」的原样不动。
        """
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        lib = self._scheduler.stickers
        exclude = set(intent_labels()) | set(SYSTEM_LABELS)
        extra = [c for c in lib.categories() if c not in exclude]
        # 识图归类优先用 sticker.classify_model，没配就回落 AstrBot 默认模型
        sec = self._sec("sticker")
        provider = self._pick_provider({"model": sec.get("classify_model", "")})
        if provider is None:
            return error_response(
                "未配置可用的识图模型，无法归类（请检查 sticker.classify_model）",
                status_code=400,
            )
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        try:
            limit = int((body or {}).get("limit", 6))
        except (TypeError, ValueError):
            limit = 6
        if limit <= 0:
            limit = 6
        targets = lib.classify_targets()
        batch = targets[:limit]
        moved, kept, failed = 0, 0, 0
        for _tag, path in batch:
            cat = await classify_image(provider, path, extra=extra)
            if cat is None:
                # 模型调用失败（不是「判不出」），单独计数
                failed += 1
                continue
            if cat == INTENT_FALLBACK:
                # 模型判不出类目，留在原地
                kept += 1
                continue
            ok, _msg = lib.move_image(path, cat)
            if ok:
                moved += 1
            else:
                failed += 1
        remaining = len(lib.classify_targets())
        data = self._scheduler.status_dict()
        data["running"] = True
        data["classify"] = {
            "total": len(targets),
            "batch": len(batch),
            "moved": moved,
            "kept": kept,
            "failed": failed,
            "remaining": remaining,
        }
        data["message"] = (
            f"本批 {len(batch)} 张：归类 {moved}，留在「其他」{kept}，失败 {failed}；"
            f"尚有 {remaining} 张未处理"
        )
        return json_response(data)

    async def page_sticker_move(self):
        """POST /astrbot_plugin_tuhengyu/sticker-move —— 手动把一张图移到另一个分类。

        body: {"name": 文件名, "from": 来源目录, "to": 目标分类}
        「表情包」页签里把卡片拖到别的分类上即可触发；本接口是它的后端。
        与「自动归类」不同，这一步不调模型、零 token，只做文件移动。
        """
        if self._scheduler is None:
            return error_response("调度器未运行（插件可能被禁用）", status_code=409)
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        body = body or {}
        name = str(body.get("name", "")).strip()
        src = str(body.get("from", "")).strip()
        dst = str(body.get("to", "")).strip()
        if not name or not dst:
            return error_response("缺少文件名或目标分类", status_code=400)
        if src and src == dst:
            return error_response("目标分类与当前相同", status_code=400)
        ok, msg = self._scheduler.stickers.move_by_name(name, dst, from_label=src)
        if not ok:
            return error_response(msg, status_code=400)
        data = self._scheduler.status_dict()
        data["running"] = True
        data["message"] = msg
        return json_response(data)

    async def page_settings_get(self):
        """GET /astrbot_plugin_tuhengyu/settings —— schema + 当前值 + 下拉选项。"""
        return json_response(
            {
                "schema": self._load_schema(),
                "values": self._config_values(),
                "options": await self._collect_options(),
            }
        )

    async def page_settings_post(self):
        """POST /astrbot_plugin_tuhengyu/settings —— 保存设置（body = 完整值对象）。"""
        try:
            payload = await web_request.json({})
        except Exception as e:
            return error_response(f"读取请求体失败：{e}", status_code=400)
        if not isinstance(payload, dict) or not payload:
            return error_response("请求体不是有效的设置对象", status_code=400)
        try:
            merged = self._merge_settings(payload)
        except Exception as e:
            return error_response(f"设置格式错误：{e}", status_code=400)
        self.config.update(merged)
        save = getattr(self.config, "save_config", None)
        if callable(save):
            try:
                save()
            except Exception as e:
                return error_response(f"保存失败：{e}", status_code=500)
        await self._refresh_persona()  # 人设/模型可能改了
        data = self._scheduler.status_dict() if self._scheduler is not None else {}
        data["running"] = self._scheduler is not None
        if not callable(save):
            data["message"] = (
                "配置已改到内存，但当前 AstrBot 不支持自动落盘（缺 save_config）。"
                "请在 AstrBot 官方插件配置页点一次「保存」，否则重启后会丢。"
            )
        return json_response(
            {
                "ok": True,
                "saved": callable(save),
                "values": self._config_values(),
                "status": data,
            }
        )
        return json_response(data)

    # ---------- 好感度页签 API ----------
    async def page_favour_list(self):
        """GET /astrbot_plugin_tuhengyu/favour-list —— 条目 + 历史 + 曲线。"""
        fav = self._favour()
        items = fav.list_all()
        hist = self._history()
        hours = self._favour_cfg().get("manual_hold_hours", 24)
        for it in items:
            it["history"] = hist.get(it["key"], 120)
            held = fav.manual_hold(it["key"], hours)
            it["hold_fields"] = held
            it["hold_until"] = fav.hold_until(it["key"], hours) if held else ""
        curve = self._curve_store().get()
        return json_response({"items": items, "curve": curve, "count": len(items)})

    async def page_favour_update(self):
        """POST /astrbot_plugin_tuhengyu/favour-update —— 手改好感 / 印象 / 关系 / 昵称。"""
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        body = body or {}
        key = str(body.get("key", "")).strip()
        if not key:
            return error_response("缺少 key", status_code=400)
        if body.get("clear_hold"):
            self._favour().clear_manual_hold(key)
            return json_response({"ok": True, "key": key, "message": "已解除手改保护。"})

        def opt(name):
            return None if name not in body else body.get(name)

        state = self._favour().set_state_by_key(
            key,
            favour=opt("favour"),
            attitude=opt("attitude"),
            relationship=opt("relationship"),
            name=opt("name"),
        )
        if state is None:
            return error_response("无效的 key", status_code=400)
        self.logger.info(
            f"[图恒宇] 页签修改 {key}: favour={state.get('favour')} "
            f"attitude={state.get('attitude')!r} relationship={state.get('relationship')!r} "
            f"手改保护={state.get('manual_fields') or []}。"
        )
        return json_response({"ok": True, "key": key, "state": state})

    async def page_favour_reset(self):
        """POST /astrbot_plugin_tuhengyu/favour-reset —— 重置（保留）或删除（整条移除）。"""
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        body = body or {}
        key = str(body.get("key", "")).strip()
        if not key:
            return error_response("缺少 key", status_code=400)
        mode = str(body.get("mode", "reset")).strip() or "reset"
        if mode == "delete":
            self._favour().remove_by_key(key)
            self._history().remove(key)
            msg = "已删除该用户记录"
        else:
            self._favour().reset_by_key(key)
            msg = "已重置该用户好感度"
        self.logger.info(f"[图恒宇] 页签{msg}：{key}（mode={mode}）。")
        return json_response({"ok": True, "key": key, "mode": mode, "message": msg})

    async def page_favour_curve(self):
        """POST /astrbot_plugin_tuhengyu/favour-curve —— 重算 / 重置 / 手改曲线。"""
        try:
            body = await web_request.json({})
        except Exception:
            body = {}
        body = body or {}
        action = str(body.get("action", "regenerate")).strip() or "regenerate"
        store = self._curve_store()
        if action == "reset":
            curve = store.reset()
            return json_response(
                {"ok": True, "curve": curve, "message": "已恢复内置默认曲线"}
            )
        if action == "save":
            raw = body.get("curve")
            if not isinstance(raw, dict):
                return error_response("curve 不是对象", status_code=400)
            curve = store.set(raw, "", "manual")
            return json_response(
                {"ok": True, "curve": curve, "message": "已保存手改曲线"}
            )
        try:
            persona, label, _name = await resolve_persona(self.context, self.config)
        except Exception:
            persona, label = "", ""
        if not persona:
            return error_response("未取到人设，无法生成曲线", status_code=400)
        sec = self._favour_cfg()
        try:
            text = await generate_curve_text(
                self.context, persona, str(sec.get("curve_model", "")).strip()
            )
        except Exception as e:
            return error_response(f"生成失败：{e}", status_code=500)
        raw = parse_curve_json(text)
        if not raw:
            return error_response("模型输出无法解析为 JSON", status_code=502)
        curve = store.set(raw, persona_fingerprint(persona), "llm")
        return json_response(
            {
                "ok": True,
                "curve": curve,
                "source": label,
                "message": "已按当前人设重算曲线",
            }
        )
