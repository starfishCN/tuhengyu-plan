"""_conf_schema.json 静态校验：JSON 合法性 + AstrBot 支持的 type 白名单。

背景：AstrBot 的 `_config_schema_to_default_config` 只认
    int / float / bool / string / text / list / file / object / template_list / dict
写错一个 type（例如 "number"）会让**整个插件加载失败**，且报错在 star_manager 深处，
从日志上只看到一串 Removed module，容易误判成"只是重载"。
所以每次改 schema 后先跑这个。
"""

import json
import sys

ALLOWED = {
    "int",
    "float",
    "bool",
    "string",
    "text",
    "list",
    "file",
    "object",
    "template_list",
    "dict",
}

PATH = "/sdcard/Download/tuhengyu-plan/plugin/astrbot_plugin_tuhengyu/_conf_schema.json"


def walk(node, path, bad):
    if isinstance(node, dict):
        t = node.get("type")
        if isinstance(t, str) and t not in ALLOWED:
            bad.append((path, t))
        for k, v in node.items():
            walk(v, "%s.%s" % (path, k), bad)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, "%s[%d]" % (path, i), bad)


def main():
    raw = open(PATH, encoding="utf-8-sig").read()
    schema = json.loads(raw)  # JSON 不合法会直接抛
    bad = []
    walk(schema, "", bad)
    if bad:
        for path, t in bad:
            print("BAD TYPE: %s = %r（支持：%s）" % (path, t, ", ".join(sorted(ALLOWED))))
        sys.exit(1)
    print("schema OK：JSON 合法，type 全部在白名单内")


main()