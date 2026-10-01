"""临时：把 WebUI 密码设为临时值以便取 JWT 做接口验证。用完必须还原。"""
import json
import shutil
import sys
from pathlib import Path

from astrbot.core.utils.auth_password import hash_dashboard_password

P = Path("/AstrBot/data/cmd_config.json")
BAK = Path("/AstrBot/data/cmd_config.json.bak_verify")

if sys.argv[1] == "set":
    shutil.copy2(P, BAK)  # 每次都刷新备份，避免用到过期副本
    d = json.loads(P.read_text(encoding="utf-8-sig"))
    d.setdefault("dashboard", {})
    d["dashboard"]["pbkdf2_password"] = hash_dashboard_password("VerifyTmp2026a")
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SET_OK", len(d["dashboard"]["pbkdf2_password"]))
elif sys.argv[1] == "restore":
    if BAK.exists():
        shutil.copy2(BAK, P)
        print("RESTORE_OK")
    else:
        print("NO_BACKUP")
