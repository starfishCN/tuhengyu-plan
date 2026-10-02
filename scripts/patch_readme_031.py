"""更新内部 README：0.3.1 记录。"""
import io

p = "/sdcard/Download/tuhengyu-plan/README.md"
s = io.open(p, encoding="utf-8").read()

ROW = (
    "| **拆分回归修复（0.3.1）** | ✓ | 上线首测即命中：插件页「设置」页签报"
    "「读不到配置结构（_conf_schema.json）」，另外三个页签正常。根因：`_load_schema` 搬进 `web/` 后"
    "仍用 `__file__` 的 dirname 定位，于是去找 `web/_conf_schema.json`，`except` 静默吞异常返回 `{}`"
    "（容器日志 `[web.settings:37]` 直证）。修法：`web/settings.py` 顶部加 `PLUGIN_ROOT` 并把路径基准改回插件根；"
    "同一补丁并进 `scripts/split_main.py`，重跑拆分脚本不再犯。全量自查 `__file__` 仅 3 处，"
    "另两处（`core/scheduler.py` 的 `parent.parent`、`main.py` 兜底目录）基准未变、仍正确。"
    "验证：容器内 `scripts/schema_check.py` 调 `_load_schema` 返回 12 个顶层键，`PLUGIN_ROOT` 指向插件根；"
    "真机 0.3.1 加载无告警。**此前无同类留档**。提交 `ada76d1` |"
)

REPS = [
    (
        "| **推送** | ✓ | 插件 `0.3.0` = `dac5edd`（代码）+ `481e98e`（文档）+ `df60919`（脚本）；",
        "| **推送** | ✓ | 插件 `0.3.1` = `ada76d1`（回归修复，代码+文档+脚本一次提交）；"
        "0.3.0 = `dac5edd`（代码）+ `481e98e`（文档）+ `df60919`（脚本）；",
    ),
    (
        "**真机状态**：插件 **0.3.0** 已部署并重载",
        "**真机状态**：插件 **0.3.1** 已部署并重载",
    ),
    (
        "日志 `Plugin astrbot_plugin_tuhengyu (0.3.0)` + `[图恒宇] 生活调度器已启动。`，无 traceback。",
        "日志 `Plugin astrbot_plugin_tuhengyu (0.3.1)` + `[图恒宇] 生活调度器已启动。`，无 traceback。",
    ),
    (
        "真机 0.3.0 加载无 traceback。见 `logs/2026-10-02-插件0.3.0模块化拆分.md`。提交 `dac5edd` |",
        "真机 0.3.0 加载无 traceback。见 `logs/2026-10-02-插件0.3.0模块化拆分.md`。提交 `dac5edd` |\n" + ROW,
    ),
]

for a, b in REPS:
    if a in s:
        s = s.replace(a, b, 1)
        print("OK  ", a[:34])
    else:
        print("MISS", a[:34])

io.open(p, "w", encoding="utf-8").write(s)
print("written", len(s))