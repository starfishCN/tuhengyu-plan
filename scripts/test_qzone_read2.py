"""QQ 空间直连方案验证 · 第二版

修正点：
  QQ 空间的 g_tk 必须由 cookie 里的 **p_skey** 计算（bkn 算法），
  而不是 SnowLuma 的 get_csrf_token（那是 QQ 客户端协议用的）。

bkn 算法：
    h = 5381
    for c in skey: h += (h << 5) + ord(c)
    g_tk = h & 0x7FFFFFFF

在 VPS 上跑。用法：python3 test_qzone_read2.py
"""
import json
import urllib.error
import urllib.parse
import urllib.request

SNOWLUMA = "http://127.0.0.1:3000"
TOKEN = "4oSJFxpVq0hjca8JpLXFstzcBUSU-XW-JBENqeIX5d4"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def onebot(action, params=None):
    body = json.dumps({"action": action, "params": params or {}}).encode()
    req = urllib.request.Request(
        SNOWLUMA + "/" + action, data=body,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["data"]


def parse_cookie(s):
    out = {}
    for part in s.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def bkn(skey):
    h = 5381
    for ch in skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


def main():
    cookies = onebot("get_cookies")["cookies"]
    uin = onebot("get_login_info")["user_id"]
    jar = parse_cookie(cookies)

    print("cookie 字段:", sorted(jar.keys()))
    print()
    for k in ("p_skey", "skey", "uin", "p_uin", "pt4_token", "RK"):
        v = jar.get(k, "<缺>")
        print("  %-10s = %s" % (k, (v[:40] + "...") if len(v) > 40 else v))
    print()

    p_skey = jar.get("p_skey", "")
    if not p_skey:
        print("!! cookie 里没有 p_skey —— 该 cookie 不是空间域的，方案要变")
        return
    g_tk = bkn(p_skey)
    print("由 p_skey 计算的 g_tk:", g_tk)
    print()

    params = {
        "uin": uin, "ftype": 0, "sort": 0, "pos": 0, "num": 5,
        "replynum": 0, "g_tk": g_tk, "callback": "_preloadCallback",
        "code_version": 1, "format": "jsonp", "need_comment": 0,
    }
    url = ("https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/"
           "emotion_cgi_msglist_v6?" + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={
        "Cookie": cookies, "User-Agent": UA,
        "Referer": "https://user.qzone.qq.com/%d" % uin,
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode(errors="replace")
        print("HTTP", r.status)
        print(raw[:800])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode(errors="replace")[:300])
    except Exception as e:
        print("FAIL", type(e).__name__, e)


if __name__ == "__main__":
    main()