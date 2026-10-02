"""与 OneBot（aiocqhttp）协议端通信的桥接层。

职责：把「向协议端要 QQ 空间 cookie」这件事封装起来，
上层的 qzone.py 只管用 cookie 去发动态，不关心它是怎么来的。

依赖 AstrBot 的公开接口：
    context.get_platform("aiocqhttp") -> Platform
    platform.get_client()             -> aiocqhttp.CQHttp
    bot.call_action(action, **params) -> dict
"""
from __future__ import annotations

import logging

logger = logging.getLogger("astrbot")

# 按优先级尝试的空间域。第一个可用即可。
QZONE_COOKIE_DOMAINS = (
    "user.qzone.qq.com",
    "qzone.qq.com",
    "h5.qzone.qq.com",
)


class OneBotBridge:
    """对 AstrBot 平台适配器的一层薄封装。"""

    def __init__(self, context):
        self.context = context
        self._cached_bot = None

    # ---------- 底层 ----------
    def bot(self):
        """取 aiocqhttp 的 CQHttp 客户端（带缓存）。"""
        if self._cached_bot is not None:
            return self._cached_bot
        try:
            platform = self.context.get_platform("aiocqhttp")
        except Exception as e:
            logger.warning(f"[图恒宇] 获取平台失败：{e}")
            return None
        if platform is None:
            return None
        getter = getattr(platform, "get_client", None)
        if not callable(getter):
            logger.warning("[图恒宇] 平台对象没有 get_client()。")
            return None
        self._cached_bot = getter()
        return self._cached_bot

    async def call(self, action: str, **params):
        """调一个 OneBot 动作。失败返回 None。"""
        bot = self.bot()
        if bot is None:
            logger.warning("[图恒宇] 拿不到 OneBot 客户端，动作 %s 跳过。", action)
            return None
        try:
            return await bot.call_action(action, **params)
        except Exception as e:
            logger.warning(f"[图恒宇] OneBot 动作 {action} 失败：{e}")
            return None

    async def call_ok(self, action: str, **params) -> bool:
        """调一个动作，只要协议端没报错就算成功。

        注意：send_poke 这类动作成功时返回 data 为 null，不能用返回值判成败。
        """
        bot = self.bot()
        if bot is None:
            logger.warning("[图恒宇] 拿不到 OneBot 客户端，动作 %s 跳过。", action)
            return False
        try:
            await bot.call_action(action, **params)
            return True
        except Exception as e:
            logger.warning(f"[图恒宇] OneBot 动作 {action} 失败：{e}")
            return False

    # ---------- 业务 ----------
    async def fetch_qzone_cookie(self) -> str:
        """取得带空间域鉴权字段的 cookie 字符串。

        关键点（实测得出）：必须带 domain 参数去要 cookie。
        不带 domain 时拿到的是客户端通用 cookie，p_skey 不在空间域上，
        空间接口会返回 code=-3000「请先登录空间」。
        """
        best = ""
        for action in ("get_cookies", "get_credentials"):
            for domain in QZONE_COOKIE_DOMAINS:
                resp = await self.call(action, domain=domain)
                cookie = _extract_cookie(resp)
                if not cookie:
                    continue
                if "p_skey=" in cookie or "skey=" in cookie:
                    best = cookie
                    break
            if best:
                break
        if not best:
            logger.warning("[图恒宇] 未能取得空间 cookie。")
        return best


def _extract_cookie(resp) -> str:
    """从 OneBot 返回里挖出 cookie 字符串（容忍多种信封）。"""
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp if "=" in resp else ""
    if not isinstance(resp, dict):
        return ""

    # 常见：{"status":"ok","retcode":0,"data":{"cookies":"..."}}
    for key in ("cookies", "cookie", "cookie_text", "data", "result"):
        if key not in resp:
            continue
        value = resp[key]
        if isinstance(value, str):
            if "=" in value:
                return value
        elif isinstance(value, dict):
            got = _extract_cookie(value)
            if got:
                return got
    return ""
