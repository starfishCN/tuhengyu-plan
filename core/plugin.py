"""配套插件：把仓库里的 astrbot_plugin_tuhengyu 预置进 AstrBot 的插件目录。

为什么专门做这一步：
    AstrBot 插件市场走 api.soulter.top 与 GitHub —— 目标机器无国际出口，
    市场根本用不了，插件必须手动放进去。预置是最省事的路径。

为什么不用额外下载：
    面板本身就是 `git clone` 整个仓库下来的，插件源码就在面板目录里的
    `plugin/astrbot_plugin_tuhengyu/`，直接拷即可。

路径为什么对得上：
    AstrBot 容器用 `-v $PWD/data:/AstrBot/data` 挂数据卷；而面板进程的 cwd
    就是面板安装目录（systemd `WorkingDirectory=/opt/tuhengyu-panel`，
    runner 未指定 cwd），所以 `./data/plugins/` 正好落进容器的插件目录。

依赖：插件只用标准库 + AstrBot API，没有 requirements 要装 —— 预置不会
引入新的失败点。
"""
import os

# 面板安装目录 = panel/ 的上一级
_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.path.join(_PANEL_DIR, "plugin", "astrbot_plugin_tuhengyu")
PLUGIN_NAME = "astrbot_plugin_tuhengyu"

# 只把文件放好，不碰容器。
# 给「④ 安装 AstrBot」步骤用 —— 那时容器还没创建，起来时会自己扫描插件目录，
# 不需要重启。
PLUGIN_STAGE_CMDS = [
    # 先确认源码在。失败即停，不会把已有插件删掉却没放回新的。
    f"test -d {PLUGIN_SRC}",
    "mkdir -p ./data/plugins",
    f"rm -rf ./data/plugins/{PLUGIN_NAME}",
    f"cp -r {PLUGIN_SRC} ./data/plugins/",
    "ls -1 ./data/plugins/",
]

# 放好 + 重启容器。
# 给独立按钮用 —— 这时 AstrBot 多半已经在跑，不重启不会加载新插件。
PLUGIN_INSTALL_CMDS = PLUGIN_STAGE_CMDS + [
    "docker restart astrbot 2>/dev/null "
    "|| echo '[图恒宇] AstrBot 容器当前不在运行 —— 插件已放好，下次启动时自动加载。'",
    "docker ps --filter name=astrbot",
]
