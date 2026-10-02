"""临时：登录 AstrBot 面板并取插件页面的 /status，用于真机验证。用完即删。"""
import json
import urllib.request

BASE = "http://127.0.0.1:6185"


def req(path, method="GET", data=None, token=None):
    url = BASE + path
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except Exception as e:  # noqa: BLE001
        return "ERR", str(e)


s, b = req("/api/auth/login", "POST", {"username": "astrbot", "password": "VerifyTmp2026a"})
print("LOGIN", s, b[:300])
tok = None
try:
    tok = json.loads(b).get("data", {}).get("token")
except Exception:  # noqa: BLE001
    pass
print("TOKEN", bool(tok))

candidates = [
    "/api/plug/astrbot_plugin_tuhengyu/status",
    "/api/astrbot_plugin_tuhengyu/status",
    "/api/plugin/astrbot_plugin_tuhengyu/status",
    "/api/plugins/astrbot_plugin_tuhengyu/status",
]
for path in candidates:
    st, bd = req(path, token=tok)
    print("GET", path, st, bd[:600])
