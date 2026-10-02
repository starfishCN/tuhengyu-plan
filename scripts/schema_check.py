"""容器内自检：设置模块能否真的读到 _conf_schema.json。

用法（在 AstrBot 容器内、cwd=/AstrBot）：
    docker exec -w /AstrBot -i astrbot python - < schema_check.py
"""
import importlib
import logging
import os

m = importlib.import_module("data.plugins.astrbot_plugin_tuhengyu.web.settings")


class _Dummy:
    logger = logging.getLogger("schema_check")


schema = m.SettingsHandlers._load_schema(_Dummy())

print("PLUGIN_ROOT", getattr(m, "PLUGIN_ROOT", "<缺失>"))
print("SCHEMA_FILE", os.path.exists(os.path.join(m.PLUGIN_ROOT, "_conf_schema.json")))
print("SCHEMA_KEYS", len(schema))
print("SAMPLE", list(schema)[:8])

print("RESULT", "OK" if schema else "FAIL（schema 为空）")