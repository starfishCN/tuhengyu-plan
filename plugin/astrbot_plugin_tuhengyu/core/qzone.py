"""QQ 空间客户端 —— 直连空间 Web 接口。

为什么不用协议端扩展：
    OneBot v11 标准协议里**没有**「发空间」动作。SnowLuma / NapCat 也不提供。
    所以只能直连空间 Web 接口。

为什么 cookie 从协议端要：
    QQ 客户端登录态就在协议端里，协议端的 get_cookies 动作可以把它吐出来。
    实测发现必须带 domain 参数（见 onebot.py 的说明）。

鉴权要素（2026-10-01 在真实环境验证通过）：
    cookie —— 空间域 cookie，含 p_skey / skey
    g_tk   —— 由 p_skey 经 bkn 算法算出，**不是** SnowLuma 的 get_csrf_token
    uin    —— 登录号

发布接口参数取自 astrbot_plugin_qzone_ultra 的生产实现（client.py: publish_mood）。
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("astrbot")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PUBLISH_URL = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com"
    "/cgi-bin/emotion_cgi_publish_v6"
)
MSG_LIST_URL = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qq.com"
    "/cgi-bin/emotion_cgi_msglist_v6"
)

HTTP_TIMEOUT = 30


def bkn(skey: str) -> int:
    """腾讯的 bkn / g_tk 算法。"""
    h = 5381
    for ch in skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


def parse_cookie(text: str) -> dict:
    out = {}
    for part in (text or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _split_jsonp(text: str):
    """空间接口返回 _preloadCallback({...}); 这里剥掉外壳。"""
    text = (text or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except Exception:
            return None
    left, right = text.find("("), text.rfind(")")
    if left == -1 or right == -1 or right <= left:
        return None
    try:
        return json.loads(text[left + 1: right])
    except Exception:
        return None


class QzoneAuth:
    """一次鉴权结果。"""

    def __init__(self, cookie: str, g_tk: int, uin: int):
        self.cookie = cookie
        self.g_tk = g_tk
        self.uin = uin

    @property
    def ok(self) -> bool:
        return bool(self.cookie) and bool(self.uin) and self.g_tk > 0


class QzoneClient:
    """发说说 / 读说说。"""

    def __init__(self, bridge):
        self.bridge = bridge
        self._auth: QzoneAuth | None = None

    # ---------- 鉴权 ----------
    async def auth(self, force: bool = False) -> QzoneAuth | None:
        if self._auth is not None and self._auth.ok and not force:
            return self._auth

        cookie = await self.bridge.fetch_qzone_cookie()
        if not cookie:
            return None
        jar = parse_cookie(cookie)
        uin_raw = jar.get("uin") or jar.get("p_uin") or ""
        uin = int(str(uin_raw).lstrip("oO") or 0) if str(uin_raw).lstrip("oO").isdigit() else 0
        skey = jar.get("p_skey") or jar.get("skey") or ""
        if not uin or not skey:
            logger.warning("[图恒宇] 空间 cookie 缺 uin 或 skey。")
            return None
        self._auth = QzoneAuth(cookie, bkn(skey), uin)
        logger.info(f"[图恒宇] 空间鉴权就绪：uin={uin}")
        return self._auth

    # ---------- 发布 ----------
    async def publish(self, content: str) -> bool:
        auth = await self.auth()
        if auth is None:
            logger.warning("[图恒宇] 空间未鉴权，放弃发布。")
            return False

        data = {
            "syn_tweet_verson": "1",
            "paramstr": "1",
            "who": "1",
            "con": content,
            "feedversion": "1",
            "ver": "1",
            "ugc_right": "1",
            "to_sign": "0",
            "hostuin": str(auth.uin),
            "code_version": "1",
            "richval": "",
            "issyncweibo": "0",
            "format": "json",
            "qzreferrer": f"https://user.qzone.qq.com/{auth.uin}",
        }
        headers = {
            "Cookie": auth.cookie,
            "User-Agent": USER_AGENT,
            "Referer": f"https://user.qzone.qq.com/{auth.uin}",
            "Origin": "https://user.qzone.qq.com",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        url = PUBLISH_URL + f"?g_tk={auth.g_tk}"

        status, text = await self._post_form(url, data, headers)
        if status is None:
            return False
        payload = _split_jsonp(text) or {}
        code = payload.get("code")
        if code == 0:
            logger.info("[图恒宇] 发空间成功。")
            return True
        if code == -3000:
            logger.warning("[图恒宇] 发空间被拒（登录态失效），将重新鉴权。")
            self._auth = None
            return False
        logger.warning(f"[图恒宇] 发空间失败：code={code} msg={payload.get('message')}")
        return False

    # ---------- 读取 ----------
    async def recent(self, num: int = 3) -> list:
        """读最近几条说说（用于回读验证）。"""
        auth = await self.auth()
        if auth is None:
            return []
        params = (
            f"uin={auth.uin}&ftype=0&sort=0&pos=0&num={num}&replynum=0"
            f"&g_tk={auth.g_tk}&callback=_preloadCallback&code_version=1"
            f"&format=jsonp&need_comment=0"
        )
        headers = {
            "Cookie": auth.cookie,
            "User-Agent": USER_AGENT,
            "Referer": f"https://user.qzone.qq.com/{auth.uin}",
        }
        status, text = await self._get(MSG_LIST_URL + "?" + params, headers)
        if status is None:
            return []
        payload = _split_jsonp(text) or {}
        return payload.get("msglist") or []

    # ---------- HTTP ----------
    async def _post_form(self, url, data, headers):
        try:
            import aiohttp
        except ImportError:
            logger.warning("[图恒宇] 缺 aiohttp，无法发空间。")
            return None, ""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, data=data, headers=headers,
                                  timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as r:
                    return r.status, await r.text(errors="replace")
        except Exception as e:
            logger.warning(f"[图恒宇] 发布请求异常：{e}")
            return None, ""

    async def _get(self, url, headers):
        try:
            import aiohttp
        except ImportError:
            return None, ""
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as r:
                    return r.status, await r.text(errors="replace")
        except Exception as e:
            logger.warning(f"[图恒宇] 读取请求异常：{e}")
            return None, ""