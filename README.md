# 图恒宇计划

> 给 bot 完整的一生。

在你的服务器上，搭一个**会自己生活的 QQ 机器人**。

---

## 它能干什么

- 💬 **聊天** —— 私聊、群聊，接你自己的大模型
- 🌙 **有作息** —— 什么时候活跃、什么时候安静
- 📝 **自己发空间** —— 动态内容由模型生成，不是复读
- 🧠 **有性格** —— 人设完全由你定义

整套系统跑在**你自己租的一台服务器**上，数据都在你手里。

---

## 快速开始

**一台全新的 Ubuntu 22.04 / 24.04 服务器**（x86_64，2 核 4G），以 root 执行：

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/starfishCN/tuhengyu-plan@main/setup.sh | bash
```

装完终端会打印一个随机生成的初始密码。浏览器访问 `http://<你的IP>:8080`，
用 `admin` + 这个密码登录，**首次登录会强制改密**，改完跟着面板点按钮。

> 更详细的步骤、每一处坑、排错表，都在 [`tutorial/`](tutorial/README.md)。

---

## 三个部分

这个项目包含三样东西，互相独立又配套：

| 部分 | 是什么 | 位置 |
|---|---|---|
| **教程** | 面向零基础，12 篇，从租机器讲到人设 | [`tutorial/`](tutorial/README.md) |
| **部署面板** | 网页工具，点按钮装 Docker / SnowLuma / AstrBot | 本仓库根目录 |
| **配套插件** | AstrBot 插件，让 bot 会自己发空间 | [`plugin/`](plugin/) |

### 系统架构

```
QQ ←→ SnowLuma ←(OneBot v11 WS)→ AstrBot ←→ 模型 / 插件
     （登录QQ）   （通信协议）      （大脑）     （性格）
```

---

## 仓库结构

```
tuhengyu-plan/
├── setup.sh                    # 一键安装入口（教程第一句用的就是它）
├── main.py                     # 部署面板主程序
├── core/                       # 面板核心逻辑
├── deploy/                     # 各组件的部署脚本
├── vendor/                     # 第三方脚本（含 NOTICE 声明）
├── requirements.txt
├── tutorial/                   # 📖 教程，12 篇
└── plugin/
    └── astrbot_plugin_tuhengyu # 🔌 配套插件
```

---

## 教程篇目

| # | 篇目 |
|---|---|
| 00 | 先读这个（花费、耗时、两大坑） |
| 01 | 租一台机器（**掏钱前先验证**） |
| 02 | 装部署面板 |
| 03 | 打开面板，装上 Docker |
| 04 | 装 SnowLuma 并登录 QQ |
| 05 | 装 AstrBot |
| 06 | 把两个连起来 |
| 07 | 给它一个脑子 |
| 08 | 装插件 |
| 09 | 常见问题 |
| 10 | 然后呢 |

**从这里开始 →** [`tutorial/README.md`](tutorial/README.md)

---

## ⚠️ 风险声明

**这个项目使用 QQ 的非官方接口。**

- 有**账号被限制**的风险。**请使用小号，不要用主号。**
- 空间发布接口是**逆向**得来的，官方随时可能更改，改动后即失效。
- 插件默认参数**刻意保守**（最短间隔 6 小时、每次 15% 概率），请勿轻易调高。
- 部署后请**及时修改所有默认密码**，不要把管理端口裸露在公网。

**使用本项目即表示你了解并自行承担上述风险。**

---

## 第三方与致谢

本项目建立在以下项目之上，**它们均非本项目原创**：

| 项目 | 作用 | 许可 |
|---|---|---|
| [SnowLuma](https://snowluma.github.io/) | QQ 协议端 | 源码可见、非商业 |
| [AstrBot](https://github.com/Soulter/AstrBot) | 机器人框架 | 见其仓库 |

`vendor/` 目录下内置的第三方脚本，其来源、改动与使用范围见
[`vendor/NOTICE.md`](vendor/NOTICE.md)。

**本项目不主张对上述第三方内容的任何权利，原作者如有异议将立即调整或移除。**

---

## 许可

本项目**原创部分**（面板、教程）采用 **MIT** 许可，见 [`LICENSE`](LICENSE)。
**AstrBot 插件**（`plugin/astrbot_plugin_tuhengyu/`）采用 **AGPL-3.0** —— 因其运行于
AGPL-3.0 的 AstrBot 之上，见插件内 `LICENSE`。
`vendor/` 目录内内置的第三方脚本**不在 MIT 范围内**，其来源与许可见
[`vendor/NOTICE.md`](vendor/NOTICE.md)。

---

## 参与

欢迎提 Issue 反馈问题。**反馈时请附上完整报错原文**，
以及 `uname -a`、`free -h`、`docker ps` 的输出 ——
「不行」「报错了」这类描述无法定位问题。