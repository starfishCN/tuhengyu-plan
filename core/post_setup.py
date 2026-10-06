"""Post-login AstrBot platform setup."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ASTRBOT_URL = "http://127.0.0.1:6185"
PLATFORM_ID = "tuhengyu-astrbot"
TOKEN_FILE = Path("data/.tuhengyu_ws_token")
WS_CONFIG = Path("vendor/snowluma_ws_config.js")


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


def _ensure_ws_token() -> str:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return token


def _configure_snowluma(token: str) -> None:
    if not WS_CONFIG.exists():
        raise RuntimeError("SnowLuma 配置脚本不存在")
    subprocess.run(["docker", "cp", str(WS_CONFIG), "snowluma:/tmp/snowluma_ws_config.js"], check=True, timeout=20)
    subprocess.run(
        ["docker", "exec", "-e", f"ASTRBOT_WS_TOKEN={token}", "snowluma", "node", "/tmp/snowluma_ws_config.js"],
        check=True,
        timeout=30,
    )
    subprocess.run(["docker", "restart", "snowluma"], check=True, timeout=30)


def _setup_sync(password: str) -> str:
    password = password.strip()
    if not password:
        raise RuntimeError("请输入当前 AstrBot 密码")
    login = _request("/api/auth/login", method="POST", payload={"username": "astrbot", "password": password})
    token = login.get("data", {}).get("token", "")
    if not token:
        raise RuntimeError("AstrBot 登录失败，请先确认 QQ 已扫码登录且凭据未被修改")
    ws_token = _ensure_ws_token()
    existing = _request("/api/v1/bots", token=token).get("data", {}).get("bots", [])
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
            "ws_reverse_token": ws_token,
        },
    }
    if any(bot.get("id") == PLATFORM_ID for bot in existing):
        _request("/api/v1/bots/by-id", method="PUT", payload=config, token=token)
        message = "AstrBot 平台配置已更新"
    else:
        _request("/api/v1/bots", method="POST", payload=config, token=token)
        message = "AstrBot 平台配置已创建"
    _configure_snowluma(ws_token)
    return message + "，SnowLuma Token 已同步"


async def setup_after_qq_login(password: str) -> str:
    return await asyncio.to_thread(_setup_sync, password)
