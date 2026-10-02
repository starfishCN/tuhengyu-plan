"""把 main.py 的单类按职责拆成 mixin 文件。

机械搬移，不改一行逻辑：只在每个方法块前面加一层 class 壳。
可重复执行：每次从 archive/main.py-0.2.28.bak 重新拆。
"""
import os
import re
import shutil

ROOT = "/sdcard/Download/tuhengyu-plan/plugin/astrbot_plugin_tuhengyu"
BACKUP = "/sdcard/Download/tuhengyu-plan/archive/main.py-0.2.28.bak"

TARGETS = [
    (
        "handlers/sticker.py",
        "StickerHandlers",
        "表情包：附带、单独发送、收集。",
        [
            "_sticker_reply_b64",
            "attach_sticker",
            "send_sticker_separately",
            "collect_sticker",
        ],
    ),
    (
        "handlers/favour.py",
        "FavourHandlers",
        "好感度：注入与回收。",
        ["_favour_cfg", "_favour", "_scope", "inject_favour", "collect_favour"],
    ),
    (
        "handlers/poke.py",
        "PokeHandlers",
        "戳一戳：判定、文本生成、回戳。",
        [
            "_poke_cfg",
            "_bridge",
            "_send_poke",
            "_poke_touch",
            "_poke_text",
            "_pick_provider",
            "on_poke",
        ],
    ),
    (
        "handlers/proactive.py",
        "ProactiveHandlers",
        "群聊主动插话：观察、判定、状态落盘。",
        [
            "_proactive_cfg",
            "_proactive_path",
            "_proactive_load",
            "_proactive_save",
            "watch_group",
            "_proactive_text",
            "_maybe_proactive",
            "test_proactive",
        ],
    ),
    (
        "diag/token.py",
        "TokenHandlers",
        "token 诊断：估算、快照、输出。",
        [
            "_TOKEN_CHARS",
            "_est_tokens",
            "_tok_path",
            "_tok_blank",
            "_tok_load",
            "_tok_roll",
            "_tok_save",
            "_tok_snapshot",
            "_tok_output",
        ],
    ),
    (
        "commands.py",
        "CommandHandlers",
        "命令：状态、测试发空间、好感度、token 诊断。",
        ["_publish_once", "status", "test_moment", "favour_status", "token_diag"],
    ),
    (
        "web/routes.py",
        "WebRoutes",
        "Web API 路由（必须以插件名为前缀）。",
        [
            "page_status",
            "page_reschedule",
            "page_test_moment",
            "page_sticker_reload",
            "page_stickers",
            "page_sticker_category",
            "page_sticker_upload",
            "page_sticker_classify",
            "page_settings_get",
            "page_settings_post",
        ],
    ),
    (
        "web/settings.py",
        "SettingsHandlers",
        "设置读写：schema 加载、取值、回落、合并。",
        [
            "_load_schema",
            "_config_values",
            "_coerce",
            "_merge_settings",
            "_collect_options",
        ],
    ),
]

KEEP = [
    "__init__",
    "initialize",
    "_refresh_persona",
    "_data_dir",
    "_data_file",
    "_sec",
    "terminate",
]

BASES = [
    ("StickerHandlers", ".handlers.sticker"),
    ("FavourHandlers", ".handlers.favour"),
    ("PokeHandlers", ".handlers.poke"),
    ("ProactiveHandlers", ".handlers.proactive"),
    ("TokenHandlers", ".diag.token"),
    ("CommandHandlers", ".commands"),
    ("WebRoutes", ".web.routes"),
    ("SettingsHandlers", ".web.settings"),
]


def split_blocks(body):
    """把类体切成「成员块」。返回 {名字: 文本}，顺序按出现先后。"""
    def_re = re.compile(r"^    (?:async )?def (\w+)")
    attr_re = re.compile(r"^    ([A-Za-z_]\w*)\s*=\s*")

    def is_own_comment(line):
        return line.startswith("    #")

    raw_starts = []
    order = []
    i = 0
    while i < len(body):
        line = body[i]
        if line.startswith("    @") or line.startswith("    def ") or line.startswith(
            "    async def "
        ):
            if line.lstrip().startswith("@"):
                j = i
                while j < len(body) and body[j].lstrip().startswith("@"):
                    j += 1
                m = def_re.match(body[j]) if j < len(body) else None
                if not m:
                    raise SystemExit("孤立装饰器，位置 %d" % j)
                raw_starts.append(i)
                order.append(m.group(1))
                i = j + 1
                continue
            m = def_re.match(line)
            if m:
                raw_starts.append(i)
                order.append(m.group(1))
                i += 1
                continue
        m = attr_re.match(line)
        if m and not line.startswith("        "):
            raw_starts.append(i)
            order.append(m.group(1))
            i += 1
            continue
        i += 1

    # 把小节注释归给下面的成员：块起点向上吞掉紧邻的注释行
    starts = []
    for s in raw_starts:
        k = s - 1
        top = s
        while k >= 0:
            if body[k].strip() == "":
                k -= 1
                continue
            if is_own_comment(body[k]):
                top = k
                k -= 1
                continue
            break
        starts.append(top)

    chunks = {}
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(body)
        text = "\n".join(body[s:e]).rstrip()
        chunks[order[idx]] = text
    return order, chunks


def main():
    path = os.path.join(ROOT, "main.py")

    if os.path.exists(BACKUP):
        shutil.copy2(BACKUP, path)
        print("RESTORE <-", BACKUP)
    else:
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        shutil.copy2(path, BACKUP)
        print("BACKUP ->", BACKUP)

    lines = open(path, encoding="utf-8").read().split("\n")
    cls_i = next(i for i, l in enumerate(lines) if l.startswith("class TuhengyuPlugin"))
    header = lines[:cls_i]
    body = lines[cls_i + 1 :]

    order, chunks = split_blocks(body)

    import_lines = [l for l in header if l.startswith(("import ", "from "))]
    # 包根文件用 .core；子目录文件（handlers/ web/ diag/）低一层，用 ..core
    deep = [l.replace("from .core", "from ..core") for l in import_lines]

    assigned = set(KEEP)
    summary = []

    for rel, clsname, desc, names in TARGETS:
        for n in names:
            if n not in chunks:
                raise SystemExit("目标 %s 引用不存在的成员：%s" % (rel, n))
            if n in assigned:
                raise SystemExit("成员 %s 被重复分配" % n)
            assigned.add(n)
        out = ['"""%s"""' % desc, ""]
        out += deep if "/" in rel else import_lines
        out += ["", "", "class %s:" % clsname]
        for n in names:
            out.append("")
            out.append(chunks[n])
        full = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        content = "\n".join(out).rstrip() + "\n"
        open(full, "w", encoding="utf-8").write(content)
        summary.append((rel, clsname, len(names), content.count("\n")))

    missing = [n for n in order if n not in assigned]
    if missing:
        raise SystemExit("未分配成员：%s" % missing)

    new = list(header)
    new.append("# 职责已按模块拆出；本文件只保留生命周期、公共辅助与注册。")
    for clsname, mod in BASES:
        new.append("from %s import %s" % (mod, clsname))
    new.append("")
    new.append(
        "class TuhengyuPlugin(" + ", ".join([b for b, _ in BASES] + ["Star"]) + "):"
    )
    for n in KEEP:
        new.append("")
        new.append(chunks[n])
    content = "\n".join(new).rstrip() + "\n"
    open(path, "w", encoding="utf-8").write(content)

    for d in ("handlers", "web", "diag"):
        p = os.path.join(ROOT, d, "__init__.py")
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8").write('"""%s 子模块。"""\n' % d)

    print("== 拆分结果 ==")
    for rel, clsname, n, nl in summary:
        print("  %-22s %-18s %2d 个成员 %4d 行" % (rel, clsname, n, nl))
    print("  %-22s %-18s %2d 个成员 %4d 行" % ("main.py", "TuhengyuPlugin", len(KEEP), content.count("\n")))
    print("成员总数：", len(order))


main()