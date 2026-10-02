"""QQ 空间直连验证 · 第三版

关键修正（来自 astrbot_plugin_qzone_ultra 的实践）：
  get_cookies 要**带 domain 参数**去要空间域的 cookie，
  否则拿到的是客户端通用 cookie，p_skey 不在空间域上，会被判「请先登录空间」。

在 VPS 上跑。用法：python3 test_qzone_read3.py
"""
import json
import urllib.error
import urllib.parse
import urllib.request

SNOWLUMA = "http://127.0.0.1:3000"
TOKEN = "4oSJFxpVq0hjca8JpLXFstzcBUSU-XW-JBENqeIX5d4"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
DOMAINS = [
    "user.qzone.qq.com",
    "qzone.qq.com",
    "h5.qzone.qq.com",
    "https://user.qzone.qq.com",
]


def onebot(action, params=None):
    body = json.dumps({"action": action, "params": params or {}}).encode()
    req = urllib.request.Request(
        SNOWLUMA + "/" + action, data=body,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


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
    print("=== 各域下 get_cookies 的返回差异 ===\n")
    best = None
    for d in DOMAINS:
        try:
            resp = onebot("get_cookies", {"domain": d})
        except Exception as e:
            print("%-28s -> FAIL %s" % (d, e))
            continue
        data = resp.get("data") or {}
        ck = data.get("cookies", "") if isinstance(data, dict) else ""
        jar = parse_cookie(ck)
        print("%-28s len=%-5d p_skey=%-5s skey=%-5s qzonetoken=%-5s uin=%s"
              % (d, len(ck), "p_skey" in jar, "skey" in jar,
                 "qzonetoken" in jar, jar.get("uin", "-")))
        if ck and best is None:
            best = ck

    print()
    if not best:
        print("!! 所有域都没拿到 cookie")
        return

    jar = parse_cookie(best)
    g_tk = bkn(jar.get("p_skey", "")) if jar.get("p_skey") else 0
    print("用于读取的 g_tk:", g_tk)
    uin = int(jar.get("uin", "o3825694788").lstrip("oO"))

    params = {
        "uin": uin, "ftype": 0, "sort": 0, "pos": 0, "num": 5,
        "replynum": 0, "g_tk": g_tk, "callback": "_preloadCallback",
        "code_version": 1, "format": "jsonp", "need_comment": 0,
    }
    url = ("https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/"
           "emotion_cgi_msglist_v6?" + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={
        "Cookie": best, "User-Agent": UA,
        "Referer": "https://user.qzone.qq.com/%d" % uin,
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode(errors="replace")
        print("HTTP", r.status)
        print(raw[:500])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode(errors="replace")[:300])
    except Exception as e:
        print("FAIL", type(e).__name__, e)


if __name__ == "__main__":
    main()