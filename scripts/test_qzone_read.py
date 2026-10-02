"""验证「直连 QQ 空间 Web 接口」方案是否可行。

思路：
  1. 从 SnowLuma 的 OneBot API 取 cookies 与 csrf token（= g_tk）
  2. 用它们调用 QQ 空间的**读取**接口，验证鉴权是否通过

本脚本只做读取验证，不发任何内容。

在 VPS 上跑。用法：python3 test_qzone_read.py
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


def main():
    cookies = onebot("get_cookies")["cookies"]
    g_tk = onebot("get_csrf_token")["token"]
    uin = onebot("get_login_info")["user_id"]

    print("uin    :", uin)
    print("g_tk   :", g_tk)
    print("cookie 长度:", len(cookies))
    print("cookie 含 p_skey:", "p_skey" in cookies)
    print("cookie 含 skey  :", "skey=" in cookies)
    print()

    # 读取接口：获取自己的说说列表（只读，不发）
    params = {
        "uin": uin, "ftype": 0, "sort": 0, "pos": 0, "num": 5,
        "replynum": 0, "g_tk": g_tk, "callback": "_preloadCallback",
        "code_version": 1, "format": "jsonp", "need_comment": 0,
    }
    url = ("https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/"
           "emotion_cgi_msglist_v6?" + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={
        "Cookie": cookies,
        "User-Agent": UA,
        "Referer": "https://user.qzone.qq.com/%d" % uin,
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode(errors="replace")
        print("HTTP", r.status)
        print(raw[:600])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode(errors="replace")[:300])
    except Exception as e:
        print("FAIL", type(e).__name__, e)


if __name__ == "__main__":
    main()