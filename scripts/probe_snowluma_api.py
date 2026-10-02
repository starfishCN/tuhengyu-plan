"""探测 SnowLuma 支持的 OneBot 扩展 API。

在 VPS 上跑（访问本机 3000 端口）。
用法：python3 probe_snowluma_api.py
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000"
TOKEN = "4oSJFxpVq0hjca8JpLXFstzcBUSU-XW-JBENqeIX5d4"

ACTIONS = [
    "get_login_info",
    "get_version_info",
    "get_cookies",
    "get_csrf_token",
    "get_credentials",
    "get_clientkey",
    "get_qq_avatar",
    "send_private_msg",
    "get_friend_list",
    "get_group_list",
    "get_status",
    "send_group_notice",
    "set_qq_profile",
    "get_profile_like",
    "get_user_status",
]


def call(action, params=None):
    body = json.dumps({"action": action, "params": params or {}}).encode()
    req = urllib.request.Request(
        BASE + "/" + action,
        data=body,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode(errors="replace")
        return raw[:300]
    except urllib.error.HTTPError as e:
        return "HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200])
    except Exception as e:
        return "FAIL %s: %s" % (type(e).__name__, e)


for a in ACTIONS:
    print("%-22s -> %s" % (a, call(a)))