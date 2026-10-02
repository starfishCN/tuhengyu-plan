import sqlite3

db = "/AstrBot/data/data_v4.db"
c = sqlite3.connect(db)
tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("TABLES:", tabs)
for t in tabs:
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
    except Exception:
        continue
    for col in cols:
        try:
            rows = c.execute(
                "select %s from %s where %s like '%%FAV%%' limit 3" % (col, t, col)
            ).fetchall()
        except Exception:
            continue
        if rows:
            print("[HIT] %s.%s  n=%d" % (t, col, len(rows)))
            for r in rows:
                print("   ", str(r[0])[:400].replace("\n", "\\n"))
