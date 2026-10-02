import json
import re
import sqlite3

db = "/AstrBot/data/data_v4.db"
c = sqlite3.connect(db)
rows = c.execute("select conversation_id, content from conversations").fetchall()
for key, content in rows:
    if not content or "%%FAV%%" not in content:
        continue
    print("=== conversation:", str(key)[:80])
    try:
        msgs = json.loads(content)
    except Exception as e:
        print("  json fail", e)
        continue
    for i, m in enumerate(msgs):
        blob = json.dumps(m, ensure_ascii=False)
        if "%%FAV%%" not in blob:
            continue
        for part in m.get("content") or []:
            txt = part.get("text") or part.get("think") or ""
            if "%%FAV%%" in txt:
                for line in txt.split("\n"):
                    if "%%FAV%%" in line:
                        print("  [msg %d role=%s] %s" % (i, m.get("role"), line.strip()[:160]))
    print("  total msgs:", len(msgs))