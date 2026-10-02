"""测国内可达的替代分发源（VPS 上跑）。

用法：python3 test_cn_sources.py
"""
import time
import urllib.request as u

CANDS = [
    ("gitee官网", "https://gitee.com/"),
    ("gitee-API", "https://gitee.com/api/v5/"),
    ("DockerHub官方", "https://registry-1.docker.io/v2/"),
    ("DaoCloud镜像", "https://docker.m.daocloud.io/v2/"),
    ("南大镜像", "https://docker.nju.edu.cn/v2/"),
    ("1ms镜像", "https://docker.1ms.run/v2/"),
    ("轩辕镜像", "https://docker.xuanyuan.me/v2/"),
]


def main():
    for name, url in CANDS:
        t0 = time.time()
        try:
            req = u.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            r = u.urlopen(req, timeout=12)
            ms = round((time.time() - t0) * 1000)
            print(f"{name:16s} OK   {r.status}  {ms}ms")
        except Exception as e:
            ms = round((time.time() - t0) * 1000)
            code = getattr(e, "code", "")
            print(f"{name:16s} FAIL {type(e).__name__} {code}  {ms}ms")


if __name__ == "__main__":
    main()