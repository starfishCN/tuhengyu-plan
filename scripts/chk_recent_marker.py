"""打印会话库里最近的 %%FAV%% 状态行，看模型到底写了什么。"""

import json
import sqlite3

c = sqlite3.connect("/AstrBot/data/data_v4.db")
rows = c.execute(
    "select conversation_id, updated_at, content from conversations order by updated_at desc limit 5"
).fetchall()
for cid, updated, content in rows:
    if not content or "%%FAV%%" not in content:
        print("conv %s  updated=%s  (无 marker)" % (str(cid)[:12], updated))
        continue
    try:
        msgs = json.loads(content)
    except Exception as e:
        print("conv %s json fail %s" % (str(cid)[:12], e))
        continue
    print("=== conv %s updated=%s msgs=%d" % (str(cid)[:12], updated, len(msgs)))
    shown = 0
    for m in reversed(msgs):
        if shown >= 6:
            break
        for part in m.get("content") or []:
            txt = part.get("text") or ""
            if "%%FAV%%" in txt:
                for line in txt.split("\n"):
                    if "%%FAV%%" in line:
                        print("   [%s] %s" % (m.get("role"), line.strip()[:120]))
                        shown += 1