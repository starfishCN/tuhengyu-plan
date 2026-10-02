"""修补：把 web/settings.py 的 schema 路径基准从「本文件目录」改回「插件根」。
同一段逻辑写进 split_main.py，防止重跑拆分脚本时回归复现。
"""
import io
import os

ROOT = "/sdcard/Download/tuhengyu-plan/plugin/astrbot_plugin_tuhengyu"
SPLIT = "/sdcard/Download/tuhengyu-plan/scripts/split_main.py"

ANCHOR = 'os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json"'
REPL = 'PLUGIN_ROOT, "_conf_schema.json"'

NOTE = (
    "# 插件根目录 = 本文件目录（web/）的上一级。\n"
    "# ⚠️ 本模块在子目录里，取插件内文件必须用这个基准，"
    "不能用 __file__ 的 dirname（会落到 web/）。\n"
    "PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
    "\n"
    "\n"
    "class SettingsHandlers:"
)


def fix(path):
    s = io.open(path, encoding="utf-8").read()
    if ANCHOR not in s:
        print("SKIP（已修或未命中）", path)
        return
    s = s.replace(ANCHOR, REPL, 1)
    s = s.replace("class SettingsHandlers:", NOTE, 1)
    io.open(path, "w", encoding="utf-8").write(s)
    print("FIXED", path)


fix(os.path.join(ROOT, "web", "settings.py"))

# 把同一补丁并入拆分脚本
s = io.open(SPLIT, encoding="utf-8").read()
if "def fix_web_settings" not in s:
    helper = '''

PLUGIN_ROOT_NOTE = (
    "# 插件根目录 = 本文件目录（web/）的上一级。\\n"
    "# ⚠️ 本模块在子目录里，取插件内文件必须用这个基准，"
    "不能用 __file__ 的 dirname（会落到 web/）。\\n"
    "PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\\n"
    "\\n\\nclass SettingsHandlers:"
)


def fix_web_settings(root):
    """拆分后修补：子目录模块取插件内文件时，路径基准要回到插件根。"""
    p = os.path.join(root, "web", "settings.py")
    s = open(p, encoding="utf-8").read()
    anchor = \'os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json"\'
    if anchor in s:
        s = s.replace(anchor, \'PLUGIN_ROOT, "_conf_schema.json"\', 1)
        s = s.replace("class SettingsHandlers:", PLUGIN_ROOT_NOTE, 1)
        open(p, "w", encoding="utf-8").write(s)


def main():'''
    s = s.replace("\ndef main():", helper, 1)
    s = s.replace(
        "    for d in (\"handlers\", \"web\", \"diag\"):",
        "    fix_web_settings(ROOT)\n\n    for d in (\"handlers\", \"web\", \"diag\"):",
        1,
    )
    io.open(SPLIT, "w", encoding="utf-8").write(s)
    print("PATCHED", SPLIT)
else:
    print("SKIP（已并入）", SPLIT)