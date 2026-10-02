"""探测 VPS 外网映射端口，判断每个端口后面是什么服务。

用法：python3 probe_mapped_ports.py
"""
import urllib.request as ur

HOST = "183.66.27.21"
PORTS = [50506, 50507, 48802, 43211]

for p in PORTS:
    url = f"http://{HOST}:{p}/"
    try:
        r = ur.urlopen(url, timeout=8)
        body = r.read(300)
        print(p, "OK", r.status, "srv=", r.headers.get("Server"), repr(body[:70]))
    except Exception as e:
        print(p, "FAIL", type(e).__name__, getattr(e, "code", ""))