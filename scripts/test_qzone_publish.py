"""QQ 空间发布验证 —— 真实发一条说说。

参数来源：astrbot_plugin_qzone_ultra/qzone_bridge/client.py 的 publish_mood()。
只在 VPS 上跑，会真的在 QQ 空间留一条动态。

用法：python3 test_qzone_publish.py "要发的内容"
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SNOWLUMA = "http://127.0.0.1:3000"
TOKEN = "4oSJFxpVq0hjca8JpLXFstzcBUSU-XW-JBENqeIX5d4"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
PUBLISH_URL = ("https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com"
               "/cgi-bin/emotion_cgi_publish_v6")
MSG_LIST_URL = ("https://user.qzone.qq.com/proxy/domain/taotao.qq.com"
                "/cgi-bin/emotion_cgi_msglist_v6")


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
    content = sys.argv[1] if len(sys.argv) > 1 else "图恒宇计划 · 插件自检"

    ck = onebot("get_cookies", {"domain": "user.qzone.qq.com"})["data"]["cookies"]
    jar = parse_cookie(ck)
    uin = int(jar.get("uin", "o0").lstrip("oO"))
    g_tk = bkn(jar.get("p_skey", ""))
    print("uin =", uin, " g_tk =", g_tk)
    print("内容 =", content)
    print()

    data = {
        "syn_tweet_verson": "1",
        "paramstr": "1",
        "who": "1",
        "con": content,
        "feedversion": "1",
        "ver": "1",
        "ugc_right": "1",
        "to_sign": "0",
        "hostuin": str(uin),
        "code_version": "1",
        "richval": "",
        "issyncweibo": "0",
        "format": "json",
        "qzreferrer": "https://user.qzone.qq.com/%d" % uin,
    }
    url = PUBLISH_URL + "?" + urllib.parse.urlencode({"g_tk": g_tk})
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Cookie": ck,
        "User-Agent": UA,
        "Referer": "https://user.qzone.qq.com/%d" % uin,
        "Origin": "https://user.qzone.qq.com",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode(errors="replace")
        print("发布 HTTP", r.status)
        print("返回:", raw[:400])
    except urllib.error.HTTPError as e:
        print("发布 HTTP", e.code, e.read().decode(errors="replace")[:400])
        return
    except Exception as e:
        print("发布 FAIL", type(e).__name__, e)
        return

    print()
    print("等 5 秒，回读说说列表验证 ...")
    time.sleep(5)

    params = {
        "uin": uin, "ftype": 0, "sort": 0, "pos": 0, "num": 3,
        "replynum": 0, "g_tk": g_tk, "callback": "_preloadCallback",
        "code_version": 1, "format": "jsonp", "need_comment": 0,
    }
    q = MSG_LIST_URL + "?" + urllib.parse.urlencode(params)
    req2 = urllib.request.Request(q, headers={
        "Cookie": ck, "User-Agent": UA,
        "Referer": "https://user.qzone.qq.com/%d" % uin,
    })
    with urllib.request.urlopen(req2, timeout=25) as r:
        raw = r.read().decode(errors="replace")
    text = raw[raw.find("(") + 1: raw.rfind(")")]
    d = json.loads(text)
    print("total =", d.get("total"))
    for m in (d.get("msglist") or [])[:3]:
        print("  -", m.get("content"), "| tid:", m.get("tid"))


if __name__ == "__main__":
    main()