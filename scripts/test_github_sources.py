"""测 SnowLuma 官方脚本依赖的 GitHub 加速站，在本机（VPS）上跑。

用法：python3 test_github_sources.py
目的：判断面板「③ 装 SnowLuma」在该机器上能否成功。
"""
import time
import urllib.request as u

RAW = (
    "https://raw.githubusercontent.com/"
    "SnowLuma/SnowLuma.Docker.Framework/main/install.sh"
)

CANDS = [
    ("ghfast.top", "https://ghfast.top/" + RAW),
    ("gh-proxy.com", "https://gh-proxy.com/" + RAW),
    ("gh.llkk.cc", "https://gh.llkk.cc/" + RAW),
    (
        "jsdelivr",
        "https://cdn.jsdelivr.net/gh/"
        "SnowLuma/SnowLuma.Docker.Framework@main/install.sh",
    ),
    ("腾讯CDN(QQ包)", "https://qqdl.gtimg.cn/qqfile/QQNT/9.9.33/release/3f89efc5/"),
    ("npmmirror(Node)", "https://npmmirror.com/mirrors/node/"),
    ("清华(docker-ce)", "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/"),
    ("raw直连", RAW),
]


def main():
    for name, url in CANDS:
        t0 = time.time()
        try:
            req = u.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            r = u.urlopen(req, timeout=12)
            data = r.read(2048)
            ms = round((time.time() - t0) * 1000)
            print(f"{name:18s} OK   {r.status}  {len(data)}B  {ms}ms")
        except Exception as e:
            ms = round((time.time() - t0) * 1000)
            print(f"{name:18s} FAIL {type(e).__name__}  {ms}ms")


if __name__ == "__main__":
    main()
