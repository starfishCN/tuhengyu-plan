"""读取 AstrBot 配置（在容器内跑）。

用法：
    docker cp read_astrbot_cfg.py astrbot:/tmp/rd.py
    docker exec astrbot python3 /tmp/rd.py
"""
import json

PATH = "/AstrBot/data/cmd_config.json"

with open(PATH, encoding="utf-8-sig") as f:
    d = json.load(f)

print("keys:", list(d.keys()))
print("platform:", json.dumps(d.get("platform"), ensure_ascii=False)[:800])
print("provider:", json.dumps(d.get("provider"), ensure_ascii=False)[:1200])
print("provider_settings:", json.dumps(d.get("provider_settings"), ensure_ascii=False)[:400])
print("provider_sources:", json.dumps(d.get("provider_sources"), ensure_ascii=False)[:1500])
print("persona:", json.dumps(d.get("persona"), ensure_ascii=False)[:300])
print("admins_id:", d.get("admins_id"))
