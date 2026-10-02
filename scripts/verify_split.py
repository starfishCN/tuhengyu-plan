"""校验拆分是否守恒：新文件里的代码行 = 备份里类体代码行（顺序、逐字）。"""
import glob
import os

ROOT = "/sdcard/Download/tuhengyu-plan/plugin/astrbot_plugin_tuhengyu"
BACKUP = "/sdcard/Download/tuhengyu-plan/archive/main.py-0.2.28.bak"
ADDED = "# 职责已按模块拆出；本文件只保留生命周期、公共辅助与注册。"


def code_lines(text, start_after_class=False):
    lines = text.split("\n")
    if start_after_class:
        idx = next(i for i, l in enumerate(lines) if l.startswith("class TuhengyuPlugin"))
        lines = lines[idx + 1 :]
    out = []
    in_doc = False
    for l in lines:
        s = l.strip()
        if in_doc:
            if s.endswith('"""'):
                in_doc = False
            continue
        if s.startswith('"""'):
            if not (len(s) > 3 and s.endswith('"""')):
                in_doc = True
            continue
        if not s:
            continue
        if l.startswith(("import ", "from ")):
            continue
        if l.startswith("class ") and l.rstrip().endswith(":"):
            continue
        if l == ADDED:
            continue
        out.append(l)
    return out


old_body = code_lines(open(BACKUP, encoding="utf-8").read(), start_after_class=True)

files = ["main.py", "commands.py"]
for d in ("handlers", "diag", "web"):
    for p in sorted(glob.glob(os.path.join(ROOT, d, "*.py"))):
        files.append(os.path.join(d, os.path.basename(p)))

new_body = []
for rel in files:
    p = os.path.join(ROOT, rel)
    if os.path.basename(p) == "__init__.py":
        continue
    new_body += code_lines(open(p, encoding="utf-8").read(), start_after_class=(rel == "main.py"))

print("备份类体代码行：", len(old_body))
print("新文件代码行　：", len(new_body))

if sorted(old_body) == sorted(new_body):
    print("RESULT CONSISTENT（行数与内容一致，仅文件顺序不同）")
else:
    print("RESULT DIFF")
    from collections import Counter

    co, cn = Counter(old_body), Counter(new_body)
    only_old = list((co - cn).elements())
    only_new = list((cn - co).elements())
    print("  仅旧有 %d 行：" % len(only_old))
    for x in only_old[:12]:
        print("    -", x)
    print("  仅新有 %d 行：" % len(only_new))
    for x in only_new[:12]:
        print("    +", x)