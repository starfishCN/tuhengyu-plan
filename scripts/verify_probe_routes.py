"""临时探针：在部署副本 main.py 的 __init__ 末尾打印已注册路由，验证后立即还原。"""
from pathlib import Path

P = Path("/opt/tuhengyu-panel/data/plugins/astrbot_plugin_tuhengyu/main.py")
CLEAN = Path("/root/main.py.clean")

import sys

if sys.argv[1] == "patch":
    src = P.read_text(encoding="utf-8")
    marker = "    # ---------- 生命周期 ----------"
    assert marker in src, "marker not found"
    probe = (
        "        try:\n"
        "            _routes = [\n"
        "                (r, m)\n"
        "                for (r, _h, m, _d) in context.registered_web_apis\n"
        "                if PLUGIN_NAME in r\n"
        "            ]\n"
        "            self.logger.info(f\"[图恒宇] PRTSDBG 已注册路由: {_routes}\")\n"
        "        except Exception as e:\n"
        "            self.logger.warning(f\"[图恒宇] PRTSDBG 读取失败: {e}\")\n"
    )
    assert "PRTSDBG" not in src, "already patched"
    P.write_text(src.replace(marker, probe + marker, 1), encoding="utf-8")
    print("PATCH_OK")
elif sys.argv[1] == "restore":
    P.write_text(CLEAN.read_text(encoding="utf-8"), encoding="utf-8")
    print("RESTORE_OK")