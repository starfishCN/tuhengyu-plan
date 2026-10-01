"""临时：验证 /stickers（表情包库分组）与 /sticker-reload。用完即删。"""
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
        with urllib.request.urlopen(r, timeout=20) as resp:
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

s, b = req("/api/plug/astrbot_plugin_tuhengyu/sticker-reload", "POST", {}, token=tok)
print("RELOAD", s)

s, b = req("/api/plug/astrbot_plugin_tuhengyu/stickers", token=tok)
print("STICKERS", s)
try:
    d = json.loads(b)
    print("  desc", d.get("desc"))
    print("  truncated", d.get("truncated"), "total_bytes", d.get("total_bytes"))
    for g in d.get("groups", []):
        print("  group", g.get("label"), "count", g.get("count"), "images", len(g.get("images", [])))
        for im in g.get("images", []):
            print("    -", im.get("name"), im.get("size"), "b64_len", len(im.get("b64", "")) if im.get("b64") else 0)
except Exception as e:  # noqa: BLE001
    print("  parse_fail", e, b[:400])