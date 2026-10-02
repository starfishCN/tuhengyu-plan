"""拿真机会话库里的历史，验证 sanitize_contexts 确实清得掉残留状态行。"""

import importlib.util
import json
import sqlite3


def load_core():
    path = "/AstrBot/data/plugins/astrbot_plugin_tuhengyu/core/favour.py"
    spec = importlib.util.spec_from_file_location("fav_core", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def count_marker(obj):
    blob = json.dumps(obj, ensure_ascii=False)
    return blob.count("%%FAV%%")


def main():
    core = load_core()
    c = sqlite3.connect("/AstrBot/data/data_v4.db")
    rows = c.execute("select conversation_id, content from conversations").fetchall()
    total_ctx = 0
    for cid, content in rows:
        if not content or "%%FAV%%" not in content:
            continue
        try:
            ctx = json.loads(content)
        except Exception as e:
            print("json fail", cid, e)
            continue
        before = count_marker(ctx)
        # 深拷贝一份，避免影响原始比对
        import copy

        work = copy.deepcopy(ctx)
        changed = core.sanitize_contexts(work)
        after = count_marker(work)
        print(
            "conv %s: marker %d -> %d, 改动 %d 处"
            % (str(cid)[:12], before, after, changed)
        )
        total_ctx += changed
    print("合计改动:", total_ctx)


main()