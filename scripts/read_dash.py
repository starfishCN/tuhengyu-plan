import json
p = "/AstrBot/data/cmd_config.json"
d = json.load(open(p, encoding="utf-8-sig"))
dash = d.get("dashboard", {})
out = {}
for k, v in dash.items():
    s = str(v)
    out[k] = (s[:32] + "...") if k.lower() == "password" else v
print(json.dumps(out, ensure_ascii=False))
print("password_len =", len(str(dash.get("password", ""))))
print("username =", dash.get("username"))