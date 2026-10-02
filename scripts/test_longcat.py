"""从 VPS 侧直连 LongCat API，验证连通性与 key 有效性。

用法（在 VPS 上）：
    python3 test_longcat.py
"""
import json
import urllib.error
import urllib.request

API_BASE = "https://api.longcat.chat/openai/v1"
KEY = "ak_2Ho53y8bf9Dp64H55h0ws5ZX1Ml4Q"
MODEL = "LongCat-2.5-Preview"


def main():
    # 1. 连通性
    try:
        r = urllib.request.urlopen(API_BASE, timeout=15)
        print("base reachable:", r.status)
    except urllib.error.HTTPError as e:
        print("base reachable: HTTP", e.code)
    except Exception as e:
        print("base UNREACHABLE:", type(e).__name__, e)
        return

    # 2. 实际对话请求
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "只回复两个字：收到"}],
        "max_tokens": 20,
    }).encode()

    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode(errors="replace")
        print("STATUS:", r.status)
        print("RAW:", raw[:1200])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code)
        print(e.read().decode(errors="replace")[:500])
    except Exception as e:
        print("FAIL:", type(e).__name__, e)


if __name__ == "__main__":
    main()