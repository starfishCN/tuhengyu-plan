"""Post-login AstrBot platform setup."""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
ASTRBOT_URL = "http://127.0.0.1:6185"
PLATFORM_ID = "tuhengyu-astrbot"


def _request(path: str, *, method: str = "GET", payload: dict | None = None, token: str = "") -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(ASTRBOT_URL + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _setup_sync(password: str) -> str:
    password = password.strip()
    if not password:
        raise RuntimeError("请输入当前 AstrBot 密码")
    login = _request("/api/auth/login", method="POST", payload={"username": "astrbot", "password": password})
    token = login.get("data", {}).get("token", "")
    if not token:
        raise RuntimeError("AstrBot 登录失败，请先确认 QQ 已扫码登录且凭据未被修改")
    existing = _request("/api/v1/bots", token=token).get("data", {}).get("bots", [])
    if any(bot.get("id") == PLATFORM_ID for bot in existing):
        return "AstrBot 平台配置已存在，跳过重复创建"
    config = {
        "bot_id": PLATFORM_ID,
        "name": "图恒宇机器人",
        "type": "aiocqhttp",
        "enabled": True,
        "config": {
            "id": PLATFORM_ID,
            "name": "图恒宇机器人",
            "type": "aiocqhttp",
            "enable": True,
            "ws_reverse_host": "0.0.0.0",
            "ws_reverse_port": 6199,
            "ws_reverse_token": "",
        },
    }
    _request("/api/v1/bots", method="POST", payload=config, token=token)
    return "AstrBot 平台配置已创建，等待 SnowLuma 连接"


async def setup_after_qq_login(password: str) -> str:
    return await asyncio.to_thread(_setup_sync, password)
