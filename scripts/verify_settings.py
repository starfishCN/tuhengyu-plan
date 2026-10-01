"""临时：验证插件页面 /status 与 /settings（GET/POST）。用完即删。"""
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
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except Exception as e:  # noqa: BLE001
        return "ERR", str(e)


s, b = req("/api/auth/login", "POST", {"username": "astrbot", "password": "VerifyTmp2026a"})
tok = None
try:
    tok = json.loads(b).get("data", {}).get("token")
except Exception:  # noqa: BLE001
    pass
print("LOGIN", s, "token", bool(tok))

s, b = req("/api/plug/astrbot_plugin_tuhengyu/status", token=tok)
print("STATUS", s)
try:
    d = json.loads(b)
    print("  running", d.get("running"), "sticker", d.get("sticker_enabled"), d.get("sticker_desc"))
except Exception:  # noqa: BLE001
    print("  raw", b[:400])

s, b = req("/api/plug/astrbot_plugin_tuhengyu/settings", token=tok)
print("SETTINGS_GET", s)
values = {}
try:
    d = json.loads(b)
    schema = d.get("schema", {})
    values = d.get("values", {})
    opts = d.get("options", {})
    print("  schema_keys", list(schema.keys()))
    print("  value_keys", list(values.keys()))
    print("  options_persona", opts.get("persona"))
    print("  options_provider", opts.get("provider"))
except Exception as e:  # noqa: BLE001
    print("  parse_fail", e, b[:400])

if values:
    s, b = req("/api/plug/astrbot_plugin_tuhengyu/settings", "POST", values, token=tok)
    print("SETTINGS_POST", s)
    try:
        d = json.loads(b)
        print("  ok", d.get("ok"))
        print("  sticker", d.get("values", {}).get("sticker"))
        print("  status_running", d.get("status", {}).get("running"))
    except Exception:  # noqa: BLE001
        print("  raw", b[:400])