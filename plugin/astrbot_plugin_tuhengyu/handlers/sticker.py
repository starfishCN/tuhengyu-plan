"""表情包：附带、单独发送、收集。"""

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
from ..core.favour import FavourStore, build_injection, parse_state_marker
from ..core.intent import FALLBACK as INTENT_FALLBACK
from ..core.intent import labels as intent_labels
from ..core.persona import resolve_persona
from ..core.proactive import build_proactive_prompt, decide_proactive
from ..core.poke import IGNORE as POKE_IGNORE
from ..core.poke import build_poke_prompt, decide as decide_poke, fallback_text
from ..core.scheduler import LifeScheduler
from ..core.stickers import SYSTEM_LABELS, read_base64, save_collected, thumb_b64


class StickerHandlers:

    # ---------- 表情包：选图（两条发送路径共用） ----------
    def _sticker_reply_b64(self, event: AstrMessageEvent) -> str | None:
        """按配置决定本条回复要不要附表情包；要则返回 base64，否则 None。

        两条发送路径（attach_sticker / send_sticker_separately）共用同一份
        概率与选图逻辑，口径完全一致，也不会各掷一次骰子。
        """
        sec = self._sec("sticker")
        if not sec.get("enabled", True):
            return None
        try:
            prob = float(sec.get("probability", 0.35))
        except (TypeError, ValueError):
            prob = 0.35
        if prob <= 0 or random.random() > prob:
            return None
        try:
            reply_text = event.get_result().get_plain_text()
        except Exception:
            reply_text = ""
        st = self._scheduler.schedule.state_at()
        path = self._scheduler.pick_sticker(f"{reply_text}{st.scene}{st.state}")
        if path is None:
            return None
        return read_base64(path)

    # ---------- 回复附带表情包 ----------
    @filter.on_decorating_result()
    async def attach_sticker(self, event: AstrMessageEvent):
        """bot 每次回复发出前，按概率在消息末尾附一张表情包。

        被动附带，不主动发消息；库为空时什么都不做。
        选图见 core/stickers.py：按「此刻状态 + 本条回复正文」里的标签名挑。
        """
        if self._scheduler is None:
            return
        sec = self._sec("sticker")
        if not sec.get("enabled", True):
            return
        if sec.get("send_separate", False):
            return  # 单独发模式：这里不附，交给 after_message_sent 另发一条
        result = event.get_result()
        if result is None or not getattr(result, "chain", None):
            return
        b64 = self._sticker_reply_b64(event)
        if not b64:
            return
        from astrbot.api.message_components import Image

        result.chain.append(Image.fromBase64(b64))

    # ---------- 回复后单独发一条表情包 ----------
    @filter.after_message_sent()
    async def send_sticker_separately(self, event: AstrMessageEvent):
        """单独发模式：bot 回复发出后，按概率再发一条只含表情包的消息。

        与 attach_sticker 互斥（靠 sticker.send_separate 分流）：关时这里是空的。
        选图与概率同 attach_sticker，共用 _sticker_reply_b64，口径一致。
        """
        if self._scheduler is None:
            return
        sec = self._sec("sticker")
        if not sec.get("enabled", True):
            return
        if not sec.get("send_separate", False):
            return
        b64 = self._sticker_reply_b64(event)
        if not b64:
            return
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Image

        try:
            await event.send(MessageChain([Image.fromBase64(b64)]))
        except Exception as e:  # 发送失败不影响主回复
            self.logger.warning(f"[图恒宇] 单独发表情包失败：{e}")

    # ---------- 对话中自动收集表情包 ----------
    @filter.event_message_type(EventMessageType.ALL)
    async def collect_sticker(self, event: AstrMessageEvent):
        """把对话里收到的图片存进表情包库（bot 自己攒表情包）。

        只存图，不改消息、不回复。同内容按 md5 去重。
        忽略 sender 是 bot 自己的事件（协议端存在把出站动作回传成入站事件的回环）。
        """
        if self._scheduler is None:
            return
        sec = self._sec("sticker")
        if not sec.get("collect_enabled", True):
            return
        try:
            if str(event.get_self_id() or "") == str(event.get_sender_id() or ""):
                return
        except Exception:
            pass
        try:
            msgs = event.get_messages()
        except Exception:
            return
        imgs = [m for m in msgs if isinstance(m, Image)]
        if not imgs:
            return

        label = str(sec.get("collect_label", "collected") or "collected").strip() or "collected"
        root = os.path.join(self._data_dir(), "stickers")
        saved = 0
        for img in imgs[:2]:  # 单条消息最多收两张，避免刷屏
            try:
                path = await img.convert_to_file_path()
            except Exception as e:  # 下载/解析失败不影响消息流程
                self.logger.debug(f"[图恒宇] 取图失败：{e}")
                continue
            if save_collected(root, path, label):
                saved += 1
        if saved:
            self._scheduler.stickers.reload()
            self.logger.info(f"[图恒宇] 对话中收集到 {saved} 张表情包 → {label}/")
