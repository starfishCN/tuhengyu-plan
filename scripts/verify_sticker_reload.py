import json, urllib.request

BASE = "http://127.0.0.1:6185"


def req(path, method="GET", body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except Exception as e:
        return "ERR", str(e)


s, b = req("/api/auth/login", "POST", {"username": "astrbot", "password": "VerifyTmp2026a"})
print("LOGIN", s, b[:200])
tok = json.loads(b)["data"]["token"]
s, b = req("/api/plug/astrbot_plugin_tuhengyu/sticker-reload", "POST", {}, tok)
print("RELOAD", s, b[:300])
