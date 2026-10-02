"""统计最近 assistant 回复的开头字/词，看是否有重复开头的习惯。"""

import json
import re
import sqlite3
from collections import Counter

c = sqlite3.connect("/AstrBot/data/data_v4.db")
rows = c.execute(
    "select conversation_id, content from conversations order by updated_at desc limit 5"
).fetchall()

texts = []
for cid, content in rows:
    if not content:
        continue
    try:
        msgs = json.loads(content)
    except Exception:
        continue
    for m in msgs:
        if m.get("role") != "assistant":
            continue
        for part in m.get("content") or []:
            t = part.get("text") or ""
            if not t.strip():
                continue
            # 去掉状态行与 think 残留
            t = "\n".join(ln for ln in t.split("\n") if "%%FAV%%" not in ln).strip()
            if t:
                texts.append(t)

print("assistant 正文条数:", len(texts))
recent = texts[-25:]
head2 = Counter(t[:2] for t in recent)
head1 = Counter(t[:1] for t in recent)
print("最近 25 条的首字统计:", head1.most_common(8))
print("最近 25 条的首两字统计:", head2.most_common(8))
print("--- 最近 12 条开头 ---")
for t in recent[-12:]:
    print("  ", t[:26].replace("\n", " "))