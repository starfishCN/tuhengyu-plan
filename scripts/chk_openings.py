"""统计最近 assistant 回复的开头字/词，看是否有重复开头的习惯。"""
import json
import re
import sqlite3
import collections

DB = "/opt/tuhengyu-panel/data/data_v4.db"
con = sqlite3.connect(DB)
cur = con.cursor()
try:
    rows = cur.execute(
        "SELECT content FROM conversations ORDER BY rowid DESC LIMIT 40"
    ).fetchall()
except Exception as e:
    print("query fail:", e)
    rows = []

texts = []
for (content,) in rows:
    if not content:
        continue
    try:
        msgs = json.loads(content)
    except Exception:
        continue
    if not isinstance(msgs, list):
        continue
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or m.get("type") or "").lower()
        if role != "assistant":
            continue
        c = m.get("content")
        if isinstance(c, list):
            parts = []
            for p in c:
                if isinstance(p, dict):
                    parts.append(str(p.get("text") or ""))
                else:
                    parts.append(str(p))
            c = "".join(parts)
        c = str(c or "")
        # 删掉 %%FAV%% 行
        c = re.sub(r"^\s*%%FAV%%.*$", "", c, flags=re.M)
        c = c.strip()
        if not c:
            continue
        texts.append(c)

print("assistant texts:", len(texts))
first_char = collections.Counter(t[0] for t in texts[:120] if t)
print("== first char ==")
for ch, n in first_char.most_common(12):
    print(f"  {ch!r}: {n}")

# 前两个字的词
prefix2 = collections.Counter(t[:2] for t in texts[:120] if len(t) >= 2)
print("== first 2 chars ==")
for ch, n in prefix2.most_common(12):
    print(f"  {ch!r}: {n}")

print("== samples ==")
for t in texts[:20]:
    print("  |", t[:40].replace("\n", " "))
con.close()
