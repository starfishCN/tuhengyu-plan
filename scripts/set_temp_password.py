import json

from astrbot.core.utils.auth_password import hash_dashboard_password

NEW = "VerifyTmp2026a"
p = "/AstrBot/data/cmd_config.json"
d = json.load(open(p, encoding="utf-8-sig"))
h = hash_dashboard_password(NEW)
d["dashboard"]["password"] = h
d["dashboard"]["pbkdf2_password"] = h
d["dashboard"]["password_storage_upgraded"] = True
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("SET_OK")