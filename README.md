# 图恒宇计划

> 本目录为「图恒宇计划」全部工作内容的唯一存放地。与 `yachiyo/`、`PRTS/` 无关，不继承任何旧资产、旧命名、旧人格。
> 接手前先读本文件。

路径：`/sdcard/Download/tuhengyu-plan/`

## 项目定位

产出**三样**东西：

1. **教程**——傻瓜式一键操作，面向**零基础**读者。
2. **部署面板**——教程的配套工具，同机一键部署 Docker / AstrBot / SnowLuma（详见「架构确认」）。
3. **配套插件**——**从零自研**（2026-10-01 定：不复用 `qzone_ultra` 旧代码，只带走功能规格；不沾旧项目）。AstrBot 插件，面向教程读者，教程会教怎么装用。
   - 目标：「给 bot 完整的一生」——让它更像活生生的人。
   - 六项行为（全溶进一个插件）：发空间 / 发表情包 / 聊天 / 群聊 / 会怼人（0.2.20 并入 favour：话归人设，插件只管时机） / 作息 + 虚拟行动安排。
   - 驱动方式：**人设驱动**。
   - 边界：聊天与群聊是 AstrBot 框架核心能力，插件只加性格与时机，不重写。

平台：**OneBot**（协议端 SnowLuma）。

## 命名（2026-10-01 定）

| 层 | 名字 |
|---|---|
| 项目正式名 | 图恒宇计划 |
| 插件包名 | `astrbot_plugin_tuhengyu` |
| 插件显示名 | 图恒宇计划 |
| 插件目录 | `plugin/astrbot_plugin_tuhengyu/` |

## 已确认约束

- 与既有项目（月見ヤチヨ / PRTS）**不沾**，独立目录、独立规范。
- 运行环境：**本地开发**，本终端可触达（可实测，区别于 PRTS/ヤチヨ 的云端不可达）。
- 教程受众：**零基础**。
- 插件是重点，功能**未定**，待用户说明。

## 架构确认（2026-10-01）

- **面板形态**：一键部署面板（WebUI）。打开后有一整套教程，点按钮即在目标服务器上部署 Docker / AstrBot / SnowLuma / OneBot。
- **部署方式**：**同机部署**。使用者在自己的 VPS 上执行一条命令，从作者 Git 仓库拉取面板并安装，之后在面板里点按钮装其余组件。
- **目标机器**：教程使用者**自己购买的**云端 Linux VPS。
- **访问方式**：公网，暂定无 HTTPS。（助手建议：涉及命令执行的界面至少要加登录认证。）
- **权限前提**：面板需 root 或 docker 组权限，才能装 Docker、起容器。

## 组件备注

### SnowLuma

- 来源：官方文档站 `snowluma.github.io`（最后更新 2026-09-26，2026-10-01 抓取）＋ GitHub README ＋ 第三方文档 `docs.yuelibot.org`。
- 定位：**独立**互操作运行时，把 hook **注入真实 QQ 进程**，转成 OneBot v11 动作与事件；内置 WebUI。
- **⚠️ 助手更正（2026-10-01）**：先前只读到 GitHub README 的「解压 `launcher.sh`」，据此写下「无 Docker 镜像」——**这是错的**。官方文档站明确：**Linux 首选 Docker**，镜像 `motricseven7/snowluma:latest`。此处以文档站为准。
- **登录方式：只支持扫码，没有 CLI 登录。** 无头环境**必须**通过 VNC / noVNC 看到 QQ 窗口才能扫码。官方 Docker 镜像自带 noVNC，远程桌面里 QQ 已自动启动。
- Docker 参数（官方）：
  - 端口：`6081`（noVNC 远程桌面，扫码用）、`5099`（WebUI）、`3000` / `3001`（OneBot）。
  - **必需**参数：`--shm-size=1g`（QQ 是 Chromium）、`--cap-add=SYS_PTRACE`、`--security-opt seccomp=unconfined`。后两个**不能省**，默认 seccomp 会拦住注入。
  - 数据卷：`qq-gateway-data:/app/data`、`qq-client-config:/app/.config`、`qq-client-data:/app/.local/share`。
- 密码获取（**仅全新数据目录首次启动输出一次**）：
  - 远程桌面密码：`docker logs snowluma 2>&1 | grep -E "远程桌面密码:|remote desktop password:" | tail -n 1`
  - WebUI 临时密码：`docker logs snowluma 2>&1 | grep -E "临时密码|initial credentials" | tail -n 1`
- **官方已有实验性一键脚本（Alpha）**：`curl -fsSL https://raw.githubusercontent.com/SnowLuma/SnowLuma.Docker.Framework/main/install.sh | bash`。与本项目面板目标**重叠**，待决策：调用它 or 自实现。
- 安全警告（官方）：**不要把 noVNC / WebUI / OneBot 端口裸暴露在公网**。
- 许可：源码可见、**非商业**许可（非 OSI 开源）。
- ⚠️ 口径冲突：Gitee 镜像 `gitsharp/SnowLuma` 的简介称其为「NapCatQQ 的第三方桌面 GUI 管理客户端」，与官方文档站（独立运行时、注入真实 QQ 进程）矛盾。**采信官方文档站**。

### 官方 install.sh 剖析（2026-10-01，源码 33011 字节，已存 `refs/snowluma_install_official.sh`）

- **docker 模式不依赖 GitHub**：流程为 `install_docker_engine → write_stack → pull_image → compose_up`；`write_stack` 由 `emit_compose_standalone()` **内联 cat 出 compose 内容**，不下载模板。GitHub 只在 **host 模式**才需要（`fetch_template_file`，取 systemd 单元）。
- `probe_network()` **只警告不退出**，GitHub 不通不影响 docker 模式。
- 脚本**自带降级链**：ghfast.top → gh-proxy.com → gh.llkk.cc → 直连；Docker 走阿里云/清华源；Node 走 npmmirror；QQ 包走腾讯 CDN。
- ⚠️ **`install_docker_engine` 会检测面板**：若机器已装宝塔/1Panel 等**且 Docker 未装**，脚本直接 `die`，不代为安装。**结论：必须先用面板②装好 Docker，再跑③。**
- 结论：**该脚本可 vendor 内置进面板**（dockr 模式脱离 GitHub 也能跑）。

### 国内网络现实（2026-10-01 实测，目标 VPS：腾讯云 NAT 型，Ubuntu 22.04）

| 类别 | 可达 | 不可达 |
|---|---|---|
| 代码托管 | **Gitee（200）** | GitHub 全系（raw / api / codeload / 直连）、**jsdelivr**、ghfast.top、gh-proxy.com、gh.llkk.cc |
| Docker registry | **DaoCloud（401）、南大（403）、1ms（401）** | Docker Hub 直连、docker.xuanyuan.me |
| 其他 | npmmirror、清华 docker-ce、腾讯 QQ CDN | — |

- 说明：registry `/v2/` 返回 **401/403 属正常**（需认证），**不代表不可用**。面板 `_probe` 判据 `status_code < 500` 正确。
- **推论一**：SnowLuma 官方脚本所有 GitHub 加速站**全挂** → 必须走"vendor 内置脚本"路线。
- **推论二**：**面板仓库自身在 GitHub，国内读者拉不下来** → `install.sh` 的分发已坏，必须镜像到 **Gitee**。
- **推论三**：镜像加速首选 **DaoCloud / 1ms**（南大返回 403，可用性存疑）。

### 目标验证机（一次性，2026-10-01）

- 地址 `183.66.27.21:53923`，Ubuntu 22.04.5 / x86_64 / 2 核 / 1.9G 内存 / 29G 盘。
- ⚠️ **非干净机器**：预装宝塔面板（8889）、nginx（80/888）、MySQL（3306）。端口与 AstrBot/SnowLuma 不冲突。
- 面板已部署并验证：`http://183.66.27.21:50505`（Basic 认证，admin / Tuhengyu2026），三功能（源测速 / 环境体检 / 日志流）**全部验通**。
- ⚠️ **该机无国际出口**（google / pypi / npm / github / CF 全不通），属廉价 NAT 型线路。见下节。
- **最终结果：面板 ①②③④ 全部验通，SnowLuma + AstrBot 双容器运行，整链路打通。**

### ⚠️ 关键坑：Docker 镜像拉不动（2026-10-01，教程必写）

**现象**：面板③执行到「拉取镜像」时失败，报 `dial tcp 172.67.220.221:443: i/o timeout`（Cloudflare IP）。

**根因**：
- 廉价 NAT 型国内 VPS 通常**无国际出口**（实测 google / pypi.org / registry.npmjs.org / objects.githubusercontent.com 全部超时）。
- 公共 Docker 镜像加速的 **registry 入口在国内**（`docker.m.daocloud.io` → 47.100.x，`docker.1ms.run` → 125.72.x，均可达），
  但**大文件 blob 托管在 Cloudflare**：
  - DaoCloud → `image-mirror.r2.daocloud.vip`（CF R2）
  - 1ms → `cloudfront-docker-cf.mrs.1ms.run`（CF）
  - 南大 → 直接 403，不对外提供 Docker Hub 代理
- 官方 install.sh 自带降级链（daemon.json → 1ms → 轩辕），**全部失败后中止**。
- 镜像 `motricseven7/snowluma:latest` 约 **697 MB**；`docker-archive` 导出后约 **1.24 GB**。

**解决方案（按推荐度）**：
1. **选 VPS 时先验证能否拉镜像**（有国际出口的线路）；
2. 给 VPS 配代理；
3. **中转**：本地 `skopeo copy docker://motricseven7/snowluma:latest docker-archive:sl.tar:motricseven7/snowluma:latest`
   → `scp` 到 VPS → `docker load -i sl.tar`（本机实测可行，1.24 GB 约 27 分钟 @0.77 MB/s）；
4. 国内对象存储 / 腾讯云 TCR 中转。

**教程前置检查（必须加）**：租机器前确认「能否 `docker pull` 一个海外镜像」，否则读者会在第③步卡死。

### SnowLuma 实机部署成功（2026-10-01，镜像经中转后）

- 镜像经 `skopeo` → `docker-archive` → scp → `docker load` 中转后，容器**正常启动**：
  - `✓ QQ 进程启动（Electron）`
  - `✓ Hook pipe connected（注入成功）`
  - `✓ WebUI 监听 5099`
- 端口：`5099`(WebUI) / `6081`(noVNC) / `3000`(OneBot HTTP) / `3001`(OneBot WS)。
- ⚠️ **未在 `.env` 设 `VNC_PASSWD` 时，VNC 无明文密码**（走 `/root/.vnc/passwd`）。已在 `.env` 补 `VNC_PASSWD` 并重建容器。
- WebUI 未改密时每次重建会**重新生成 bootstrap 密码**，需从 `docker logs` 取。
- 内存：1.9 GB 机器上 SnowLuma 约占 756 MB，**可用约 1 GB，偏紧**。

### 官方脚本补丁：P1 + P2（`vendor/apply_patches.py`，2026-10-01 均已实测生效）

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| **P1** | 正版 Docker CE 被判为 snap 版，脚本中止 | `docker info \| grep -qi 'snap'` 误匹配 Docker 29.x 的 `io.containerd.snapshotter.v1`（"snapshotter" 含 "snap"） | 删宽泛匹配，只保留 `/snap/` 路径判断 |
| **P2** | 镜像已中转载入，③ 仍去 registry 查更新并失败 | `pull_image()` 直接 `docker pull`，不查本地 | pull 前加 `docker image inspect ... \|\|` 短路 |

P2 生效证据（③ 输出）：`✓ 镜像 motricseven7/snowluma:latest 已存在，跳过拉取`。

### AstrBot 实机部署成功（2026-10-01，镜像经中转后）

- 镜像 `soulter/astrbot:latest`，registry 视图 **696 MB**；中转链 `skopeo` → `docker-archive`（1.97 GB）→ `gzip -1`（748 MB）→ scp → `docker load`（4.04 GB）。
- **无需补丁**：`astrbot.py` 用 `docker run`（非 `docker pull`），本地有镜像即不联网。
- 启动：`AstrBot started. Running on http://0.0.0.0:6185`，用户名 `astrbot`。
- ⚠️ 日志中 `api.soulter.top` 超时、`UpdateServiceError` 均因**无国际出口**，不影响运行。

### 整链路串联成功（2026-10-01，里程碑）

```
QQ  ⇄  SnowLuma  ←(OneBot v11 WS)→  AstrBot  ⇄  插件 / 人设
```

- 两容器初始跨网络 → `docker network connect snowluma_default astrbot` 打通，可用容器名互访（`ws://astrbot:6199/ws` 得以解析）。
- AstrBot 侧 `aiocqhttp`（UI 里叫「OneBot v11」）：反向 WS `0.0.0.0:6199`、token `tuhengyu2026`。
- SnowLuma 侧新增 wsClient：URL `ws://astrbot:6199/ws`、token `tuhengyu2026`、角色 `Universal`、消息格式 `数组`、重连 5000 ms。
- **双向日志时间戳对齐**（同为 `12:43:44`）：
  ```
  SnowLuma  [OneBot.WS-Client] [wsclient-1] connected ws://astrbot:6199/ws
  AstrBot   aiocqhttp(OneBot v11) 适配器已连接。
  ```

### 端口映射（NAT，实测通过）

| 外网 | 内网 | 服务 |
|---|---|---|
| 50505 | 8080 | 部署面板 |
| 50506 | 6081 | noVNC（扫码登录 QQ） |
| 50507 | 5099 | SnowLuma WebUI |
| 48802 | 3000 | OneBot HTTP |
| 43211 | 6185 | AstrBot WebUI |

### 链路已通但机器人尚不应答

AstrBot 未配 AI 模型 → 消息送达但无回复。**下一步须配「模型提供商」。**

## 许可与第三方内容（2026-10-01）

- **内置的 SnowLuma 官方脚本**（`panel/vendor/snowluma_install.sh`）：SnowLuma 为「源码可见、**非商业**」许可（非 OSI 开源）。
  - 处置：**选项③** —— 保留内置分发，但附 `panel/vendor/NOTICE.md` 声明：来源、抓取日期、补丁改动、**非商业用途**、**不主张权利、不声称获授权**、原作者有异议即移除。
  - 理由：国内实测所有 GitHub 加速源全挂，运行时下载不可行。
- **本项目原创部分**（面板 / 教程 / 插件）许可方式**待定**。

## 代码托管（2026-10-01）

- **Gitee（主）**：`https://gitee.com/starfishCN/tuhengyu-plan` —— 面向国内读者。
  - 一键安装命令（教程首句）：
    ```bash
    curl -fsSL https://gitee.com/starfishCN/tuhengyu-plan/raw/main/install.sh | bash
    ```
  - **已在 VPS 上实测 `git clone` 成功**（国内直连可用）。
- **GitHub（镜像）**：`https://github.com/starfishCN/tuhengyu-plan`。
- `install.sh` 源策略：**先 Gitee，失败回退 GitHub**（已实测）。
- 已推送 commit：`6a6e725`（实机验证修复）、`9f96704`（NOTICE）、`8f652eb`（install.sh 换源）、`0558964`（插件 v0.2.0）、`77d2808`（教程 12 篇）、`66e6d94`（仓库首页 README）、`db799d2`（插件作息骨架）、`b74c494`（插件第 4 条：后台行为接日程）、`bebe71f`（第 4 条收尾）、`0be1554`（插件 0.2.3：自定义页面）。
  - 注：远端另有面板阶段八一批提交（`ec3cce1`、`af4b985` 等，共 10 个），由其他途径推送，本地 VPS 仓库经 `rebase` 已同步。
- **仓库首页 README**：源文件为本地的 `README-repo.md`，推送时复制为仓库根的 `README.md`。
  - ⚠️ 本地 `README.md`（本文件）**含验证机凭据，不入库**，只作内部交接文档。
  - 两份 README 用途不同：本文件面向 PRTS/后续接续者；`README-repo.md` 面向仓库访客。

## 推送凭据（2026-10-02 更换令牌；本文件不入库）

| 远端 | 令牌 | 用法 |
|---|---|---|
| Gitee | 不落明文（2026-10-02 轮换） | `git push https://starfishCN:<TOKEN>@gitee.com/starfishCN/tuhengyu-plan.git main` |
| GitHub | 不落明文（2026-10-02 轮换） | `git push https://<TOKEN>@github.com/starfishCN/tuhengyu-plan.git main`（fine-grained PAT，需 Contents 读写） |

- 明文不再写入本文件（本文件曾因被误推触发 GitHub Push Protection）。
- 现值存放位置：本机 `/root/_gitee_clone`（origin=Gitee、github=GitHub）与验证机 `/opt/tuhengyu-panel`（origin=Gitee），用 `git remote -v` 取。
- 旧值（`a24258ae…` Gitee、`github_pat_11AQSX2XA0rmkVN34ruuYG…` GitHub）：已于 2026-10-02 判定泄露并轮换，**后台吊销状态待确认**，勿再使用。
- 全过程见 `logs/2026-10-02-凭据轮换与泄露处置.md`。

- 验证机（腾讯云 `183.66.27.21`）**无国际出口**，只能推 Gitee。
- 本机（Ubuntu 终端环境）**可达 GitHub**（200），推 GitHub 须在本机执行。
- 本机镜像仓库：`/root/_gitee_clone`（origin=Gitee、github=GitHub，两个 remote 均已带令牌）。
- 推送前必检：仓库根 `README.md` 必须为访客版（`README-repo.md` 的副本），**不含任何凭据**。2026-10-02 曾因误用内部版覆盖而触发 GitHub Push Protection。
- 首次 push GitHub 报 HTTP 408：先 `git config http.version HTTP/1.1` + `git config http.postBuffer 524288000`，重试即成功。
- `/sdcard` 为 FUSE 挂载，**不能**在其上 clone（写 .git pack 失败）；clone 走 home 目录。

## 教程（`tutorial/`，2026-10-01 完成）

面向零基础读者，**12 个文件、约 2100 行**。全部步骤来自实测，踩过的坑均已前置预警。

| # | 文件 | 内容 |
|---|---|---|
| — | `README.md` | 总纲：架构、两个提前警告、篇目表 |
| 00 | `00-先读这个.md` | 花费、耗时、两大坑、术语表（说人话） |
| 01 | `01-租一台机器.md` | 配置要求、**掏钱前先验证的 curl 命令**、端口映射 |
| 02 | `02-装部署面板.md` | 一键命令、启动、systemd 自启 |
| 03 | `03-打开面板装上Docker.md` | 环境体检、网络源测速、装 Docker |
| 04 | `04-装SnowLuma并登录QQ.md` | 装容器、取密码、远程桌面、扫码登录 |
| 05 | `05-装AstrBot.md` | 装容器、取密码、改密 |
| 06 | `06-把两个连起来.md` | 容器互通、双向配置、日志验证、排错 |
| 07 | `07-配模型.md` | 国内可用 API、provider 配置、推理模型坑 |
| 08 | `08-装插件.md` | 手动安装步骤、触发测试、人设占位 |
| 09 | `09-常见问题.md` | 按现象分类的排错表 |
| 10 | `10-然后呢.md` | 人设写法、调参、安全、风控、致谢 |

**写作原则**：术语用比方不用术语解释；命令可直接复制；风险不回避；
口吻与工程文档区分（面向小白用第二人称、短句）。
详见 `logs/2026-10-01-教程正文.md`。

## 面板功能：读取初始凭据（2026-10-01）

**问题**：小白装完面板后，找不到 AstrBot / SnowLuma / noVNC 的初始密码。

**实测的三个来源**（推翻了教程原稿的两处写法）：

| 密码 | 来源 | 特性 |
|---|---|---|
| noVNC | 容器环境变量 `VNC_PASSWD` | ✅ 稳定 |
| AstrBot | 日志 `Initial password` | ⚠️ 仅首次启动 |
| SnowLuma | 日志 `initial credentials` | ⚠️ 仅首次；**未改密时重启会变** |

**实现**：`panel/core/credentials.py`（新增，三段探测 + `gather()`）
+ `core/runner.py` 新增 `run_capture()`（取回输出而非刷进日志，密码不入日志流）
+ `main.py` 新增折叠区「找不到密码？点这里读初始凭据」（含端口表、复制按钮）。

**踩坑**：`tail -1` 在本机某些管道上下文报 `option used in invalid context`，
改 `tail -n 1`；`sed` 的 `[: ]*` 有 POSIX 字符类歧义，改 `: *`。
**这两个坑都会导致管道静默失败，表现为「读不到密码」，极难查。**

**部署注意**：VPS 上 `/opt/tuhengyu-panel` 的 git remote 仍是 **GitHub**，
在无国际出口的机器上 `git pull` 会卡 **130 秒**。改 remote 为 Gitee 或直接 scp 覆盖。

**遗留（方案 B，未做）**：与其「抓」，不如**部署时写死** —— 由面板生成密码并写入，
则永远可查。当前为方案 A（只抓取）。

## 技术选型（2026-10-01 定）

- 面板框架：**NiceGUI**（纯 Python，前后端一体，支持实时日志流）。
- SnowLuma 版本策略：**追最新**——面板运行时通过 GitHub Releases API 取 latest。
- AstrBot 部署：**官方 Docker 镜像**。

## 组件部署参数

### AstrBot

来源：官方文档 `docs.astrbot.app/deploy/astrbot/docker.html`（2026-10-01 抓取）。

- 镜像：`soulter/astrbot:latest`；中国大陆加速：`m.daocloud.io/docker.io/soulter/astrbot:latest`。
- 端口：`6185`（WebUI）、`6199`。
- 数据卷：`$PWD/data:/AstrBot/data`；时区挂载 `/etc/localtime`、`/etc/timezone`。
- 初始密码见启动日志，用户名通常 `astrbot`。
- 官方另有 Compose 方案，含「和 NapCat 一起部署」一节。

### 连接关系

```
QQ  ⇄  SnowLuma（OneBot v11 协议端）  ⇄  AstrBot（框架）  ⇄  模型
```

## 待定项（未确认，禁止脑补）

- [ ] 面板代码仓库地址（使用者那条命令从哪拉取面板）
- [ ] 面板监听端口
- [ ] 面板的认证方案与是否上 HTTPS
- [ ] SnowLuma Releases 的 asset 命名规则（面板要按 API 动态选包）
- [ ] 插件第一版之外的功能细化（第一版已定：发空间 + 作息 + 调度器骨架）
- [ ] 插件授权方式（LICENSE）
- [ ] 插件与教程的关系（教具 or 独立交付物）
- [x] 教程主线与篇目（已完成，见下节「教程」）
- [ ] 目录名「tuhengyu-plan」为助手暂定，用户可改
- [ ] 面板与 SnowLuma 自带 WebUI 的职责划分（倾向：面板只管「装 + 起」，管理交给 SnowLuma 自己的 WebUI）

## 目录结构

**待定**。结构由内容决定，等插件功能清单明确后再建子目录，不预先造空目录。

## 插件指令与页面（指令大全）

### QQ 里可用的指令

| 指令 | 作用 | 备注 |
|---|---|---|
| `/图恒宇` | 查看插件状态：调度器是否运行、当前作息、此刻在干嘛、上次发说说 | 只读 |
| `/图恒宇测试` | 立刻手动发一条 QQ 空间动态 | 验证链路用，会烧一次 token |
| `/图恒宇好感` | 查看自己当前的好感度 / 印象 / 关系 | 只读；需 favour 启用 |
| `/token诊断` | 看最近一次 LLM 请求的 token 构成 + 今日累计用量 | 0.2.21 新增 |
| `/图恒宇插话 群号` | 让它在指定群接一句（忽略概率与冷却） | **0.2.24：仅管理员私聊可用**；群里发同一指令不响应；非管理员回「仅管理员可用」 |

指令前缀以 AstrBot 的指令设置为准（默认按唤醒词规则）。

### 插件页面

AstrBot WebUI → 插件 → 图恒宇计划，页面在后端接口前缀 `/api/plug/astrbot_plugin_tuhengyu` 下：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/status` | 结构化运行状态 |
| POST | `/reschedule` | 丢弃旧作息并按人设重算 |
| POST | `/test-moment` | 立即发一条空间动态 |
| POST | `/sticker-reload` | 重扫表情包目录 |
| GET | `/stickers` | 表情包库（按意图分组） |
| POST | `/sticker-category` | 新建表情包分类 |
| POST | `/sticker-upload` | 上传表情包 |
| POST | `/sticker-classify` | 识图自动归类 |
| GET / POST | `/settings` | 读取 / 保存设置 |

## 当前状态与接续点（2026-10-01 归档）

### 进度

```
阶段一  面板建设          ✓ 完成
阶段二  实机验证 ①②③④     ✓ 完成（真实 VPS）
阶段三  链路串联          ✓ 完成（QQ ⇄ SnowLuma ⇄ AstrBot）
阶段四  仓库与分发        ✓ 完成（Gitee 主 + GitHub 镜像，实测国内 clone 可用）
阶段五  让 bot 说话        ✓ 完成（端到端验收通过，延迟 3.8s）
阶段六  插件第一版        ✓ 完成（发空间打通，真实环境验证）
阶段七  教程正文          ✓ 完成（12 篇，约 2100 行，面向零基础）
阶段八  面板打磨          ✓ 完成（凭据读取 / v0.3 界面 / 安全默认 / 自建登录页 / 动画 / 毛玻璃）
                              末次 commit `ec3cce1`。**2026-10-01 用户决定暂时搁置，转入插件。**
 阶段九  插件扩展          ◐ **当前主线**（详见 `logs/2026-10-01-插件作息骨架.md`）
        ├ 第 1 条  schema 定稿        ✓ 完成（7 顶层字段 / 5 个 object 分组）
        ├ 第 2–3 条 作息骨架 + 状态   ✓ 完成（`core/schedule.py` 新建，真机重载验证通过）
        ├ 第 4 条  后台行为接日程     ✓ 完成（含收尾：文案去重 + 词表开放配置；本地自测 25 项 + 真机/QQ 实测均过）
        ├ 插件自定义页面（运行状态）  ✓ 完成（0.2.3：pages/status + status/reschedule Web API；服务端全链路实测）
        ├ 页面调试按钮 + 模式提示      ✓ 完成（0.2.4）
        ├ 人设来源读 AstrBot 人格      ✓ 完成（0.2.5：select_persona 下拉 + 页面检测 + 失败原因透出；真机 /status 验证）
        ├ 测试按钮无反应修复            ✓ 完成（0.2.6：iframe sandbox 无 allow-modals，改页内两步确认）
        ├ 手动发说说丢人设修复          ✓ 完成（0.2.7：_publish_once 补齐 persona 传参）
         ├ 第 5 条 a 表情包             ✓ 完成（0.2.8：回复被动附带；目录即标签 + 关键词命中 + 随机，零 embedding）
         ├ 第 5 条 a 收尾 WebUI 页签      ✓ 完成（0.2.9：页面三页签 + 设置可折叠；对话中自动收集表情包）
         ├ 第 5 条 a 补充 表情包页签      ✓ 完成（0.2.10～0.2.12：第 4 个页签按标签分类展示库存；Pillow 缩略图预览，大图 / GIF 均可显示；对话收集已实证 collected×18）
         ├ 第 5 条 a 再补充 情绪分类   ✓ 完成（0.2.13：表情包按情绪 6 类分类；按 AI 回复情绪选图；单独发 / 一起发开关；概率可调）
         ├ 第 5 条 a 再补充 WebUI 增删   ✓ 完成（0.2.14：页签按分类分组展示；新建分类 + 上传图片）
         ├ 第 5 条 a 改为意图 + 识图归类  ✓ 完成（0.2.15：情绪→意图 8 类；大模型识图自动归类，限 6 张/批；WebUI 自动归类按钮）
         ├ 第 5 条 好感度系统（自研）    ✓ 完成（0.2.16：core/favour.py 三维状态；注入 system prompt + `%%FAV%%` 单行回写、整行全量剥离；绕开第三方 favourpro 只剥首块导致的状态行泄漏）
         ├ 第 5 条 戳一戳反应            ✓ 完成（0.2.16：core/poke.py；收/发 Poke 已核实；冷却 30s、连戳阈值 3；文字走模型，拿不到模型回落台词池）
         ├ 第 5 条 回戳改走动作          ✓ 完成（0.2.17：poke 段被 SnowLuma 判 UNSENDABLE_TYPE 拒收，改走 OneBot `send_poke` 动作，群/私聊自动路由）
         ├ 第 5 条 戳一戳修复          ✓ 完成（0.2.18：`send_poke` 成功返回 `data:null`，原判据 `resp is not None` 误判成功为失败；文字改走 `provider.text_chat`，原 `resolve_provider_id("")` 取不到 id 导致全程回落台词池；普通关系不再静默只回戳）
         └ 第 5 条 人设注入位置          ✓ 完成（0.2.19：人设只放 system 时 LongCat 无视、回「在呢，有什么事吗？」客服腔；改拼进 user 消息 + 禁客服腔指令，18/18 稳定在角色内）
         └ 第 5 条 怼人并入 favour       ✓ 完成（0.2.20：独立「怼人」项否掉——话归人设、插件只管时机；core/favour.py 的 build_injection 在 favour<-10 区间插入「可冷淡、可怼回去」时机许可，favour<-50 加强，说什么一律由人设决定）
         ├ 戳一戳概率化                 ✓ 完成（0.2.21：回戳与回话各自掷骰——可能只回戳、只说话、两样都做、或干脆不理；新增 speak_prob 配置）
         ├ token 诊断                   ✓ 完成（0.2.21：/token诊断；输出 system_prompt / 上下文 / 工具的字符与折算 token + 今日累计，存 token_stats.json）
         └ 第 5 条 主动发言（群聊插话）     ✓ 完成（0.2.22：core/proactive.py；醒着才说话、极低概率、接群友的话；热聊也接，不设冷场判据；冷却 + 每群每日上限 + 一次 tick 最多一句）
阶段十  收尾杂项          ⬜ 改密 / LICENSE
```

### ⚠️ 接续点（2026-10-01 20:07 离开时状态）

- [ ]（2026-10-02 记，**不急**）**新 bot 跑在无限上下文配置**（`max_turns: -1`）。`/token诊断` 实测上下文 22 → 26 条随历史线性增长，单轮 ≈7.7k token（system_prompt 5011 + 工具 1271 + 上下文 ≈1400）。建议：`max_turns: 16` + `overflow_strategy: truncate_by_turns`，或保留 -1 改走 `llm_compress`。博士指示「先记住，不急」。

**已完成**：插件第 1 条（schema）、第 2–3 条（作息骨架 + 状态命令）、**第 4 条（后台行为接日程）及其收尾**、**插件自定义页面（0.2.3 运行状态面板）**、**页面调试按钮与人设/作息模式提示（0.2.4）**、**人设来源改为读 AstrBot 人格 + 下拉选人格（0.2.5）**。第 4 条与收尾均已本地自测 + 真机重载 + 冒烟通过；`/图恒宇` 与 `/图恒宇测试` 已在 QQ 实测。工作日志：`logs/2026-10-01-插件后台行为接日程.md`、`logs/2026-10-01-插件第4条收尾与WebUI核查.md`、`logs/2026-10-01-插件自定义页面.md`（含 0.2.4 续篇）、`logs/2026-10-01-插件0.2.5人设来源改造.md`。

**插件 WebUI 核查（结论）**：

- **配置界面：已有**，不用写代码 —— AstrBot 按 `_conf_schema.json` 自动生成表单。真机配置 `/AstrBot/data/config/astrbot_plugin_tuhengyu_config.json` 已生成，8 顶层键 / 6 分组，且分组为嵌套 dict。
- **自定义插件页面：已做（0.2.3 + 0.2.4）** —— `pages/status/` 运行状态面板：此刻作息 / 触发概率 / 时段表，**「操作」区含「重算作息」与「测试发一条」两个按钮**，并按人设是否填写、作息是否自动生成显示前置告警。后端注册 `/{插件名}/status`(GET)、`/{插件名}/reschedule`(POST)、`/{插件名}/test-moment`(POST)。服务端全链路实测通过（页面发现 / HTML 下发 / 静态资源 / 三条 API 路由注册与调用均验证）。**浏览器端实际渲染未验，需博士在 WebUI 里点开看一眼。**

**真机状态**：插件 **0.3.8** 已部署并重载（运行副本 `data/plugins/` + 仓库副本 `plugin/` 双写）；日志 `Plugin astrbot_plugin_tuhengyu (0.3.8)` + `[图恒宇] 生活调度器已启动。`，无 traceback。备份 `/tmp/bak_plugin_037`（VPS）。推送链：0.3.0=`dac5edd`、0.3.1=`ada76d1`、0.3.2=`ba0c786`、0.3.3=`98fa730`、0.3.4=`2f7dc1d`、0.3.5=`8643d8a`、0.3.6=`1592765`（代码）+ `b84bcce`（文档）、0.3.7=`d265c1b`（代码）+ `6500d2a`（文档）、0.3.8=`1b6e3c8`。VPS 仓库 `/opt/tuhengyu-panel` 本轮已 `git fetch` + `reset --hard origin/main` 对账至 `d265c1b`（此前停在 `ada76d1` 且工作树脏；`data/` 未受影响，双副本仍 IDENTICAL，`scripts/split_main.py` 的一次性守卫已恢复）。`/status` 真机返回（0.2.5 时验证）：`persona_set: true`、`persona_label: "人格「测试」（跟随默认）"`、`persona_preview` 为真实人设正文、`persona_pending: true`、`schedule_error: "生成失败"`。（0.2.6 起日志为 `作息：读盘（7 段）`，说明期间已配好模型并生成过作息。）

**人设来源（0.2.5 定案）**：① 插件配置 `persona_id` 指定的人格 → ② 否则跟随 AstrBot 当前默认人格（换人格自动跟上）→ ③ 再叠加插件配置 `persona_prompt`（补充文本，可选）→ ④ 都没有则空串，回落内置 `DEFAULT_SYSTEM_PROMPT`。`resolve_persona(context, config)` 返回 `(text, label, name)`。**根因**：此前插件人设只有一条来源——插件自己的 `persona_prompt`，与 AstrBot 的「人格」无任何关联，所以博士换人格插件「检测不到」。

**⚠️ 验证机当前阻塞（环境问题，非代码）**：该机 AstrBot **尚未配置可用的对话模型**（`context.get_using_provider()` 取不到），故 `generate_schedule_text` 直接 warning 返回空串，作息停在 `conservative`（09:00–23:00 醒），`schedule_error: 生成失败`。**需在 AstrBot 里配好 provider 后点页面「重算作息」**，才能生成贴人设的作息。

**⚠️ AstrBot WebUI 密码仍未解决**。记录在案的 `Nrvn5CCJ9P9rAR3ghsgDbg1b` 登录返回 **401**（用户名 `astrbot` 正确）。本轮为跑端到端验证临时改过密码（`scripts/verify_setpw.py set`），验完已 **restore 并清理**（`/tmp/verify_setpw.py`、`/tmp/verify_status.py` 均已删）。**博士需自行确认/重置 WebUI 密码**。

| 事项 | 状态 | 说明 |
|---|---|---|
| **推送** | ✓ | 插件 `0.3.8` = `1b6e3c8`（双端一致：Gitee `6500d2a..1b6e3c8`、GitHub `6500d2a..1b6e3c8`）；`0.3.7` = `d265c1b`（双端一致：Gitee `b84bcce..d265c1b`、GitHub `b84bcce..d265c1b`）；`0.3.6` = `1592765`（代码）+ `b84bcce`（文档）（双端一致：Gitee `8643d8a..b84bcce`、GitHub `8643d8a..b84bcce`）；`0.3.5` = `8643d8a`（双端一致：Gitee `2f7dc1d..8643d8a`、GitHub `2f7dc1d..8643d8a`）；`0.3.4` = `2f7dc1d`（双端一致：Gitee `98fa730..2f7dc1d`、GitHub `98fa730..2f7dc1d`）；`0.3.3` = `98fa730`；`0.3.2` = `ba0c786`；`0.3.1` = `ada76d1`；`0.3.0` = `dac5edd`（代码）+ `481e98e`（文档）+ `df60919`（脚本）；上版 0.2.28 = `ab01f61`，已推 Gitee（`origin`，验证机直推 `a9a09f8..ab01f61`）+ GitHub（`github`，本机 `/root/_gitee_clone` 推 `a9a09f8..ab01f61`）。此前的 0.2.15 为 `27475d6`（Gitee `3ede07d..27475d6`；GitHub `af4b985..27475d6` 由本机 fast-forward 补推）。再前 `3ede07d`(0.2.14)、`43eb192`(0.2.13)、`bf29d87`(0.2.12)、`ca711e3`(0.2.10)、`11a434e`(0.2.9) |
| `/图恒宇` QQ 实测 | ✓ | 回执含「触发概率：0.15 × 状态 1.0 → 0.15」 |
| `/图恒宇测试` QQ 实测 | ✓ | 内容确已发到空间（0.2.4 时） |
| **下拉选人格/模型** | ✓ | `_special: select_persona`（新增 `persona_id`）、`select_provider`（`chat_private.model`/`chat_group.model`/`schedule.generate_model`/`moment.provider_id` 均为）→ AstrBot 自动渲染为下拉 |
| 人设来源改造（0.2.5） | ✓ | 改读 AstrBot 人格；`/status` 实测 `persona_set: true`、`persona_label` 正确 |
| **说说带人设（0.2.7）** | ✓ | `_publish_once` 补齐 persona 传参；**博士已实测确认口吻符合** |
| **表情包（0.2.8）** | ✓ | 回复被动附带（`on_decorating_result`）；目录即标签 + 关键词命中 + 随机，零 embedding；`/status` + `sticker-reload` 真机 200。**待博士放图后实测附图** |
| **三页签 + 设置（0.2.9）** | ✓ | 页面改「状态 / 操作 / 设置」；设置按 `_conf_schema.json` 渲染、分组可折叠、可保存；`GET/POST /settings` 真机 200（schema 9 键、provider/persona 下拉有值）。**浏览器端渲染未验** |
| **表情包页签（0.2.10～0.2.12）** | ✓ | 第 4 个页签按标签（情绪目录）分类展示库存；0.2.12 起用 Pillow 缩略图预览（320px JPEG），大图 / GIF 均可显示，响应体积降约 80%（实测 2.0MB → 405KB）。`GET /stickers` 真机 200。**浏览器端渲染未验** |
| **表情包情绪分类（0.2.13）** | ✓ | 表情包按情绪 6 类（开心 / 难过 / 生气 / 惊讶 / 无语 / 害羞 + 其他）归并展示；按 AI 回复情绪选图（关键词规则，零 token）；`send_separate` 单独发 / 一起发开关；概率 `probability` 设置页可调。`/status` `/settings` `/stickers` 真机 200。**浏览器端渲染未验** |
| **表情包 WebUI 增删（0.2.14）** | ✓ | 表情包页签按分类分组展示；新增「新建分类」「上传图片」（base64 走 bridge）；后端 `POST /sticker-category`、`POST /sticker-upload` 真机 200（新建 / 上传 / 去重 400 / 非法名 400 均验）。**浏览器端渲染未验** |
| **意图类目 + 识图归类（0.2.15）** | ✓ | 分类维度情绪→意图 8 类（拒绝/道歉/攻击/亲昵/赞同/提问/认输/害羞）；新增 `core/intent.py`（关键词，选图零 token）、`core/classify.py`（大模型识图归类）；`POST /sticker-classify` 分批（默认 6 张/批）真机 200，实测把 collected×18 判出意图（认输/害羞等），LongCat-2.5-Preview 支持视觉输入；错误键 `sticker.emotion_match`→`intent_match`。**浏览器端渲染未验** |
| **好感度 + 戳一戳（0.2.16）** | ✓ | 自研 `core/favour.py`（好感 / 印象 / 关系，`favour.json`，`FavourStore` 夹逼 -100~100）与 `core/poke.py`（冷却 / 连戳 / 睡眠 / 好感分档决策，纯函数可单测）。回写格式改为单行 `%%FAV%% 好感 | 印象 | 关系`，`finditer` 收全部 + `sub` 整行剥离（第三方 favourpro 的 bug 是只剥首块，多块残留会泄漏）。新增 `@filter.on_llm_request` / `on_llm_response` / `event_message_type(ALL)` 三处 handler；私聊戳事件用 `event.should_call_llm(True)` 掐掉默认 LLM。离线单测 30 项全过；真机 0.2.16 加载无报错、模块可导入、`GET /settings` schema 含 `favour`/`poke`。**QQ 实戳未验**（需真人戳一次）|
| **回戳改走动作（0.2.17）** | ✓ | 排查确认 AstrBot 的 `Poke(id=).toDict()` 发的是 go-cqhttp 旧式 `{"type":"poke","data":{"type":"126","id":...}}`；SnowLuma 的 poke 段用 `subType`、不读 `id`，且 `assertWindowShakeSendPolicy` 限其**仅私聊且须唯一段**，群聊直接抛 `UNSENDABLE_TYPE`。改为 `main.py:_send_poke()` 经 `OneBotBridge.call("send_poke", user_id=, group_id=)`（SnowLuma 有 `send_poke` 动作，群/私聊自动路由）。真机 0.2.17 加载无报错、容器内可编译。**QQ 实戳未验**（需真人戳一次）|
| **戳一戳修复（0.2.18）** | ✓ | 真机实戳后暴露两处：① `send_poke` 成功时 `data:null`，`resp is not None` 把成功判成失败（HTTP 直调 send_poke retcode 0 已证动作本身可用）；② 戳一戳文字走 `resolve_provider_id(context, "")` 取不到 id 直接 return，从未调模型，「在呢」属回落台词池。改为 `OneBotBridge.call_ok()` + `context.get_using_provider().text_chat()`；普通关系由「抛硬币（纯回戳 / 说话）」改为「必答一句，多数同时回戳」。离线 13 项校验全过，真机 0.2.18 加载无报错。**QQ 实戳复验未做** |
| **人设注入位置（0.2.19）** | ✓ | 实测在同一模型（LongCat-2.5-Preview）上做对照：同 6375 字人设**只放 system** 时，6 次采样有 2 次回「嗯？」「在呀，有什么事吗？」这类客服腔；**拼进 user 消息**后 t=1.0/0.8/0.5 各 6 次共 18 次全部在角色内（「哦呀…神明大人」「八千代」）。故 `build_poke_prompt` 新增 `persona` 参数、拼在 user 正文前，`text_chat` 不再传 `system_prompt`。离线校验过，真机 0.2.19 加载无报错。**QQ 实戳复验未做** |
| **怼人并入 favour（0.2.20）** | ✓ | 第 5 条余下的独立「怼人」项否掉：话归人设、插件只管时机。`build_injection` 在 favour<-10 时插入「可以冷淡、可以怼回去：短句，带笑不带脏字，一两句收场，不追着吵。说什么，按你自己的人设来。」，favour<-50 加强为「可以直接怼回去、也可以干脆不搭理」。连戳场景已由 0.2.16 的 `SNAP` 分支覆盖。离线 12 项校验全过，双副本 md5 一致，真机 0.2.20 加载无报错。**低好感口气变化未验**（需把某人好感刷到 -10 以下）|
| **戳一戳概率化 + token 诊断（0.2.21）** | ✓ | ① `core/poke.py` 的 `decide()` 把「回戳」与「回话」拆成两次独立掷骰（关系好 0.70/0.90、普通 `poke_back_prob`/`speak_prob`、关系差 0.15/0.30），四态 BOTH/SILENT_POKE/TEXT/IGNORE 都可能出现；新增配置 `speak_prob`。② 新增 `/token诊断`：在 `on_llm_request` 抓 system_prompt / 上下文 / 工具构成，`on_llm_response` 累计输出，按 2.06 字符/token 折算，存 `token_stats.json` 按日归零。离线 26 项全过，双副本 md5 一致，真机 0.2.21 加载无报错 |
| **群聊主动插话（0.2.22）** | ✓ | 口径按博士：群聊热聊里也插嘴、接群友的话、只要醒着、概率极低；不做冷场判据。新增 `core/proactive.py`（`decide_proactive` 纯函数 + `build_proactive_prompt`）；`LifeScheduler` 加 `add_action`，附加行动不叠加 `act_probability`；`watch_group` 记每群最近 20 条 / 30 分钟；发送走 OneBot `send_group_msg`；状态存 `proactive.json`；新命令 `/图恒宇插话`。默认关，离线 32 项全过，真机 0.2.22 加载无报错。**`send_group_msg` 未实测** |
| **群聊观察常开（0.2.23）** | ✓ | 实机反馈：群里聊了不少但 `/图恒宇插话` 提示没记到聊天——`watch_group` 曾把「记录」与 `enabled` 绑死，默认关时一条也不记。改为记录常开，`enabled` 只控自动插话；运行实例开关置 true。提交 `1901c8a` |
| **插话指令走管理员通道（0.2.24）** | ✓ | `/图恒宇插话 群号` 改走管理员私聊（方案 B）：群里不响应、回执只在私聊，权限用 `event.is_admin()`，名单取全局 `admins_id`（已由占位改为 `2664648140`）。提交 `899c61d` |
| **插话上下文可见化（0.2.25）** | ✓ | 反馈「插话不像看了上下文」，先加诊断：指令回执附「它看到的最近几条」；提示词收紧为「必须接上面某一条具体的话，不要聊没出现过的话题」。**群聊记录仅在内存，重启即清空**。提交 `bdfa20f` |
| **插话口癖硬要求（0.2.26）** | ✓ | 反馈「插话人设掉了」。对照实验证实：人设取到了，但被「像热心群友接话」的任务盖过 →通用关心话。正文加「必须出现角色自称/口头禅/特有称呼」后，离线采样 14/14 回到角色内（措辞通用，未硬编码角色）。提交 `0212fcc` |
| **一次戳回两条修复（0.2.27）** | ✓ | 真机反馈：群聊戳一次回两条（一条带人设一条不带）。日志显示收到两条入站戳事件，第二条 sender = bot 自身——回戳动作被协议端回传成事件，插件当新戳处理。加守卫忽略 `uid == self_id`。提交 `a9a09f8` |
| **插件自检修复 + 图形化（0.2.28）** | ✓ | 自检 19 项（bug / 冗余 / 臃肿 / 面向客户）。本轮修 P0–P2：① 设置保存不再静默成功（缺 `save_config` 时回执 `saved:false`，前端提示改去官方页保存）；② `_coerce` 空值回落 schema 默认值，不再写 0；③ 识图模型可配（新增 `sticker.classify_model`），「调用失败」与「判不出」分开计数，前端归类回执提示查模型；④ 表情包两条发送路径抽 `_sticker_reply_b64` 公共函数；⑤ 配置分组取值抽 `_sec`；⑥ `json`/`os` import 上提顶层；⑦ 收集表情包忽略 bot 自身回传。文档重写：插件 README（原停在 0.2.7）、`metadata.yaml` desc、安装路径落实。C 类大重构（main.py 拆分）留待单独版本。提交 `ab01f61` |
| **插件模块化拆分（0.3.0）** | ✓ | C1–C3 一次做完：`main.py` 1396 → 183 行，业务拆为 `handlers/`（sticker / favour / poke / proactive）、`commands.py`、`web/`（routes / settings）、`diag/token.py` 共 8 个 mixin，主类多继承组装。先读 AstrBot 源码确认装饰器在导入期注册、卸载按 `data.plugins.<目录>` 前缀清理，故 mixin 与单文件注册行为等价。守恒校验：类体代码行 1168 = 1168；handler 12 = 12；双副本 `diff -r` 一致；真机 0.3.0 加载无 traceback。见 `logs/2026-10-02-插件0.3.0模块化拆分.md`。提交 `dac5edd` |
| **拆分回归修复（0.3.1）** | ✓ | 上线首测即命中：插件页「设置」页签报「读不到配置结构（_conf_schema.json）」，另三页签正常。根因：`_load_schema` 搬进 `web/` 后仍按 `__file__` 的 dirname 推路径，去找 `web/_conf_schema.json`，`except` 静默吞异常返回 `{}`。修法：加 `PLUGIN_ROOT`（上退两层）作路径基准，`scripts/split_main.py` 同步补丁。全库模板 12 键读取正常，真机 0.3.1 无告警。见 `logs/2026-10-02-插件0.3.0模块化拆分.md`「回归」一节。提交 `ada76d1` |
| **表情包手动拖动归类（0.3.2）** | ✓ | 表情包页每个分类区块成为拖拽落点，卡片拖进别的分类即归类；拖进「其他」＝回散图区。后端新增 `POST /sticker-move` 与 `StickerLibrary.move_by_name`（带来源目录防同名歧义），`page_stickers` 每组下发 `drop` 落点。纯文件移动、零 token。接口层直调验证：移动 200 / 同目标 400 / 缺参 400 / 找不到 400；双副本 IDENTICAL、`assets/` 未被误删；真机 0.3.2 加载无 traceback。同时给 `scripts/split_main.py` 加一次性守卫（检测到 `handlers/` 默认拒绝重跑，须 `SPLIT_FORCE=1`）。见 `logs/2026-10-02-插件0.3.2表情包拖拽归类.md`。提交 `ba0c786` |
| **拖拽改用指针事件（0.3.3）** | ✓ | 0.3.2 真机实测「有拖拽无反应」。排查：部署无误（容器内 `app.js` 含拖拽代码）、缓存排除（`plugin_page_service.py` 下发 `Cache-Control: no-store`）→ 判定 HTML5 原生拖放在触屏 / WebView 里不触发 `drop`（只实现了拖起）。改指针事件自实现：`pointerdown` → 位移超 8px → 浮层跟随 → `pointerup` 用 `elementFromPoint` 命中分类；卡片加 `touch-action:none`。`node --check` 通过（脚本 / 模块两模式）。见 `logs/2026-10-02-插件0.3.2表情包拖拽归类.md`「0.3.3 修正」一节。提交 `98fa730` |
| **空分类留落点 + 归类改「暂存→保存」（0.3.4）** | ✓ | 两条真机反馈：① 把分类下唯一一张图拖走 → 分类消失、拖不回来；② 每拖一张闪一下。修法：后端 `groups_by_intent()` 改为**含空目录**（新增 `dirs()` 扫一级子目录，内置意图类目「有图或目录存在」即返回，用户分类按 `dirs()` 全量返回，余下兜底），页面落点留住；前端改**暂存 + 「保存归类」**——拖动只改本地（`pendingMoves` 暂存、`.pending` 角标、`origTag` 记原始目录、空分类放 `.gallery-empty` 占位），点保存才逐条 `POST /sticker-move` 并只重载一次。验证：`node --check` + `py_compile` 通过；库行为单测 5 项过；真实数据（容器内 20 张）空目录 `道歉` 返回、`其他` 2 张；双副本 IDENTICAL、`assets/` 保留；真机 0.3.4 加载无 traceback。见 `logs/2026-10-02-插件0.3.2表情包拖拽归类.md`「0.3.4」一节。提交 `2f7dc1d` |
| **表情包卡片去文件名（0.3.5）** | ✓ | 博士验收后要求：卡片下方「文件名 · 尺寸 · 缩略」对使用者无意义，去掉。`stickerCard()` 删 `figcaption` 段并移除随之失效的 `fmtSize()`；`style.css` 删 `.sticker-card figcaption`。`img.alt` 保留文件名（无障碍 / 排障），预览失败占位保留。`node --check` 通过、双副本 IDENTICAL、真机 0.3.5 加载无 traceback。见 `logs/2026-10-02-插件0.3.2表情包拖拽归类.md`「0.3.5」一节。提交 `8643d8a` |
| **模块化拆分回归：全插件 handler 静默失效（0.3.6）** | ✓ | 真机发 `/图恒宇好感` 等命令无回执；戳一戳、表情包、群聊插话、好感注入一并失效（消息全被 LLM 接走），日志无 traceback。根因：0.3.0 拆分后 handler 的 `handler_module_path` 指向子模块，AstrBot 两处按它精确匹配（`waking_check` 用 `star_map[module_path]` 判激活 → 查不到即整体跳过；加载期只对主模块 handler 绑实例）双双失配。修法：`main.py` 新增 `_bind_submodule_handlers()`（`initialize()` 首行），把子模块路径别名到主模块 metadata，并把 handler `module_path` 归一 + `functools.partial(raw, self)` 绑实例。验证：真机注入 `/图恒宇好感` → `好感度 0｜印象：中立｜关系：陌生人`；无斜杠 → 同上且附表情包（证明 `on_decorating_result` 恢复）；`/图恒宇` → `调度器运行中。`；无 `TypeError`；`star_map` 已含子模块别名；探针已清。见 `logs/2026-10-02-插件0.3.0模块化拆分.md`「回归」一节。提交 `1592765` |
| **好感度长期不变修复（0.3.7）** | ✓ | 真机反馈「好感无变动」。零侵入查会话库 `data_v4.db`：rowid=1 思考链写 「No need for the FAV line since there's no relationship change needed」（模型主动省略）；rowid=2 正文确有 `%%FAV%% 1 | 友善 | 陌生人`，且 `favour.json` 已写入 `2681711819 → favour:1 / 友善`——证明写入链路通。真因：提示词给了「本轮无需改动就整行省略」的口子，推理模型多数轮次判「无需改动」就整行省略 → 不落盘。修法：`core/favour.py` 的 `build_injection` 去掉省略口子，改为「每一轮都必须输出状态行，即使无变化也照写当前值，不得省略」。版本 0.3.7；双副本 IDENTICAL；容器重启后 `Plugin astrbot_plugin_tuhengyu (0.3.7)` 加载无 traceback。提交 `d265c1b` |
| **好感度页签 + 人设驱动变化曲线（0.3.8）** | ✓ | 博士要求「好感度单独一个页签 + 按人设调 LLM 设变化曲线 + 看每人好感/状态/关系」，拍板「都要」（LLM 参数曲线 + 历史折线图两者都做）、「可改」（页签可编辑）。交付：第 5 页签「好感度」——表格（昵称/QQ/好感+档位/印象/关系/最近更新，可就地编辑、重置、删除）+ 曲线面板（信息 + Canvas 折线 + 档位与幅度 chip）；`core/favour.py` 新增 `DEFAULT_CURVE`/`normalize_curve`/`persona_fingerprint`/`parse_curve_json`/`band_of`/`CurveStore`/`HistoryStore`，`build_injection` 支持曲线参数；`core/llm.py` 新增 `generate_curve_text`；`handlers/favour.py` 懒加载曲线（人设指纹不变不重算）并记历史与昵称；新增 4 条路由 `favour-list`(GET)/`favour-update`/`favour-reset`/`favour-curve`(POST)。验证：`py_compile` + `node --check` 通过；四文件双副本 md5 IDENTICAL；容器重启 `Plugin (0.3.8)` 无 traceback；真数据目录 store 冒烟（list_all/update/set_by_key/remove/history 去重/CurveStore set-reload-reset）全过；路由层直调 `page_favour_list` 返回真实 items + 默认曲线。折线图用原生 Canvas 自绘，**不用外链 CDN**（目标机无国际出口）。见 `logs/2026-10-02-插件0.3.8好感度页签.md` |
| **对话收集（0.2.9）已实证** | ✓ | 真机库中出现 `collected×18`（1.1～3.0MB 的 GIF/JPG），即对话中自动收集链路的真机证据 |
| **对话收集表情包（0.2.9）** | ✓ | `collect_sticker()` 取消息里的 `Image` 存入 `stickers/collected/`（md5 去重、5MB 上限）；离线单测通过。**真机需有人在群里发图才可实测** |
| 生成作息路径 | ✓ | 0.2.6 起日志 `作息：读盘（7 段）` → 模型已配好、作息已生成 |
| **「测试发一条」按钮** | ✓ | 0.2.6 修复：iframe sandbox 无 `allow-modals` → `window.confirm` 恒 false 导致无反应；改页内两步确认 |
| 插件自定义页面（0.2.3） | ✓ | 服务端链路全通；**浏览器端渲染未验**，需人在 WebUI 点开 |
| AstrBot WebUI 密码 | ⬜ | 记录值已失效（401），待博士确认/重置 |

**下一步（0.2.25 后）**：第 5 条六项行为**全部完成**——发空间（0.2.4）／表情包（0.2.8 被动 + 0.2.9 收集 + 0.2.13 分类 + 0.2.14 WebUI 增删）／聊天／群聊／会怼人（0.2.20 并入 favour）／作息 + 虚拟行动（0.1.x 骨架起）＋主动插话（0.2.22，0.2.23 观察常开，0.2.24 管理员私聊通道，0.2.25 上下文可见化，0.2.26 口癖硬要求）。戳一戳另修 0.2.27（忽略 bot 自身回传的戳事件）。

**接下来是验证轮，不再是开发轮**：
1. 插话上下文复验——重启后先在群里说两句，再私聊 `/图恒宇插话 群号`，看回执「它看到的最近几条」是否合理、生成的话是否真接得上（群聊记录仅内存，重启即清）。
2. `/token诊断` 真机输出复验（需先有一条走 LLM 的消息）。
3. QQ 实戳复验——确认能出现「没反应 / 只回戳」的少数情况、回话带角色口吻。
4. 好感度实际变化、低好感口气变化（需把某人刷到 -10 以下）。
5. 浏览器端人眼渲染（插件自定义页面）。
6. AstrBot WebUI 密码待确认/重置。

主动路径（`act()` 里主动发图 / 插话）仍可按「每种行动各带适用条件与冷却」的形状接。

**本轮新增/改动**（0.2.5 人设来源读 AstrBot 人格 + 下拉 + 失败原因透出）：

```
core/persona.py              新增（约 66 行）。resolve_persona(context, config) → (text, label, name)
core/schedule.py             +set_persona/_persona_text；_persona() 改用注入值；+pending_change()（新语义）；+_last_error/last_error()
core/scheduler.py            +persona_text/label/name、set_persona()；status_dict() +persona_label/persona_name/persona_preview/persona_pending/schedule_error
core/llm.py                  generate_moment_text() +persona 形参（优先级 persona->persona_prompt->DEFAULT）
main.py                      +_refresh_persona()，在 initialize/_publish_once/status/page_status/page_reschedule 前调用
_conf_schema.json            +persona_id（type:string, _special:select_persona, 默认空=跟随默认）；persona_prompt 降级为「补充」
pages/status/index.html      +人设展示行 + #persona-note 提示条；重算说明改为「读当前人设（来自 AstrBot 人格）」
pages/status/app.js          渲染 persona_label / persona_pending / schedule_error 三分支告警
pages/status/style.css       +.hero-note
metadata.yaml / 插件 README   版本 0.2.5
scripts/verify_status.py     新增（临时验证：登录面板取 /status）
```

**人设机制（0.2.5 新增知识，必读）**：

- AstrBot 人格由 `context.persona_manager`（`PersonaManager`，`/AstrBot/astrbot/core/persona_mgr.py`）管理。
  - `get_persona_v3_by_id(pid)`：空 id → `None`；`"default"` → 内置 `DEFAULT_PERSONALITY`；否则在 `personas_v3` 里按 **name**（非 id）匹配。
  - `async get_default_persona_v3(umo=None)`：读 `agent_runner.config.persona.persona_id`，取不到回落 `DEFAULT_PERSONALITY`。
  - `Personality` 是 TypedDict（`/AstrBot/astrbot/core/db/po.py`），含 `prompt`、`name` 等键。
- **配置下拉控件**：`_special` 字段让配置项渲染为专用控件，官方已支持 `select_provider` / `select_persona` / `select_knowledgebase` / `select_plugin_set` 等。插件侧填 `_special` 即得下拉。**面板自身（NiceGUI）不做这些下拉**，插件配置由 AstrBot 按其 `_conf_schema.json` 自动渲染。

上一轮（0.2.4 调试按钮 + 模式提示）：
```
main.py                      抽 _publish_once()，/图恒宇测试 改为复用；+page_test_moment 与 /{插件名}/test-moment(POST)
core/scheduler.py            status_dict() +persona_set / schedule_auto / manual_hours
pages/status/index.html      新增「操作」面板（重算作息 + 测试发一条，各带说明）
pages/status/app.js          +reschedule() / testMoment()（window.confirm）/ renderTestResult()；人设与模式告警
pages/status/style.css       +83 行（.action* / .btn-warn）
metadata.yaml / 插件 README   版本 0.2.4
```

上一轮（0.2.3 自定义页面）：
```
pages/status/{index.html,style.css,app.js}  新增。状态面板 + 重算作息
.astrbot-plugin/i18n/zh-CN.json             新增。pages.status.title = 运行状态
main.py / core/scheduler.py / core/schedule.py / metadata.yaml 见 0.2.3 段
```

再上一轮（第 4 条收尾）：`core/schedule.py` brief() 去重、`core/scheduler.py` +bias_table()/词表配置、`_conf_schema.json` +4 项、版本 0.2.2，详见 `logs/2026-10-01-插件第4条收尾与WebUI核查.md`。

**关键知识（必读）**：

1. **`_conf_schema.json` 的 `object` 存成嵌套 dict** → `config["schedule"]["manual_hours"]`。旧代码全用扁平 key，**不改读不到值**。
2. **插件在 VPS 上的位置**：`/opt/tuhengyu-panel/data/plugins/astrbot_plugin_tuhengyu/`（容器内 `/AstrBot/data/plugins/`）。git 仓库是 **`/opt/tuhengyu-panel`** 本身。
3. **插件备份**：VPS `/root/backup_plugin_20261001_190910`（作息版）；本轮覆盖前另存 `/root/backup_plugin_20261001_191735`。
4. **VPS 可直连**：本终端 `sshpass` + `ssh` 均可用，`sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 53923 root@183.66.27.21`（凭据见「验证机」表）。插件在 VPS 有**两份**：运行副本 `/opt/tuhengyu-panel/data/plugins/astrbot_plugin_tuhengyu/` 与仓库副本 `/opt/tuhengyu-panel/plugin/astrbot_plugin_tuhengyu/`，更新时要同步两处。
5. **仓库 remote 已是 Gitee**（`https://gitee.com/starfishCN/tuhengyu-plan.git`，分支 `main`）；push 需用户名 + 私人令牌，服务器未存凭据（`/root/.git-credentials` 不存在）。
6. **插件配置界面不用自己写** —— AstrBot 按 `_conf_schema.json` 自动渲染表单；配置文件落在容器 `/AstrBot/data/config/astrbot_plugin_tuhengyu_config.json`（分组为嵌套 dict）。
7. **自定义插件页面机制**（2026-10-01 打通，官方文档 `dev/star/guides/plugin-pages.html`）：
   - 页面落点 `pages/<page_name>/index.html`，**自动发现**（目录扫描）；page_name 非空、无 `/`、无 `\`、非 `.`/`..`、不以 `.` 开头。
   - 页面在 WebUI 内以**受限 iframe** 加载，服务端返回 HTML 时自动注入 `/api/plugin/page/bridge-sdk.js`（不用手写 `<script>`），并把 HTML 里的**相对路径改写成绝对路径 + `asset_token`**。
   - 前端 `bridge.apiGet(endpoint, params)` / `apiPost(endpoint, body)`，endpoint 是**插件内相对路径**（不含插件名）。
   - 后端 **`context.register_web_api(route, handler, methods, desc)`，route 必须自带插件名前缀**：`/astrbot_plugin_tuhengyu/status`。
     原因：URL `/api/v1/plugins/extensions/<plugin.name>/<endpoint>` 会被整段交给 `_match_registered_web_api` 做正则全匹配，而 `register_web_api` **不会**自动补前缀。
   - handler 从 `astrbot.api.web` 取 `request`（上下文代理），返回 `json_response` / `error_response` 等；路由里的 `<name>` 占位会作为关键字参数传入。
   - 页面标题：`.astrbot-plugin/i18n/<locale>.json` 的 `pages.<page_name>.title`；缺省回落为 page_name。
   - 改静态资源刷新页面即可；**新增/删除页面目录要重载插件**。
   - 现状：`pages/status/`（运行状态面板 + 操作区），API 为 `/{插件名}/status`(GET)、`/{插件名}/reschedule`(POST)、`/{插件名}/test-moment`(POST)。
   - **方法不匹配与路由不存在返回同一个体**（`未找到该路由`，HTTP 200），所以拿 GET 去「探测某 POST 路由是否存在」是**无效**的。要验注册，用临时探针打印 `context.registered_web_apis`（脚本 `scripts/verify_probe_routes.py`，patch/restore 两态）。
8. **端口有两层，别混**：宿主**监听**端口（AstrBot `6185` / SnowLuma `5099`、`6081` / OneBot `3000`）与**公网映射**端口（面板 `50505`、AstrBot `43211`、noVNC `50506`、SnowLuma `50507`、OneBot `48802`、SSH `53923`）是两回事 —— 映射由云网关做，**VPS 本机不监听公网端口**。所以从 VPS 内部 `127.0.0.1:43211` 会 `ConnectionRefused`，本机调试只能走 `127.0.0.1:6185`；公网访问则用 `43211`。验证机表里列的是公网映射端口。
10. **插件页跑在受限 iframe 内，sandbox = `allow-scripts allow-forms allow-downloads`**（前端 dist 里 `class:"plugin-page-frame"` 的 iframe）。
    - **无 `allow-modals`** → `window.confirm()` / `alert()` / `prompt()` 会被浏览器**静默忽略**，`confirm()` 恒返回 `false`。**不要在插件页用原生弹窗**，要确认就做页内两步确认（见 0.2.6 的 `testMoment`）。
    - **无 `allow-same-origin`** → 页面处于**不透明源**，不要依赖 localStorage / cookie / 同源直连接口；与后端的通信一律走注入的 `window.AstrBotPluginPage`（bridge-sdk）。
    - bridge-sdk 由服务端以**经典 script** 注入在 `</body>` 前（`plugin_page_service.py:741`），执行早于 `type="module"` 的 app.js，故 app.js 运行时 bridge 已存在。
    - 静态资源改动**刷新页面**即可生效；仅新增/删除页面目录才需重载插件。
11. **部署双副本必须用 `rsync -aI --delete`**。`rsync -a` 默认按 **size + mtime** 快速判断，`0.2.6`→`0.2.7` 这种**同名等长**改动会被静默跳过（0.2.7 首次部署即踩此坑：`main.py` 更新了、`metadata.yaml` 没更新）。
    标准命令：
    ```bash
    rsync -aI --delete /tmp/plugin_new/astrbot_plugin_tuhengyu/ /opt/tuhengyu-panel/data/plugins/astrbot_plugin_tuhengyu/
    rsync -aI --delete /tmp/plugin_new/astrbot_plugin_tuhengyu/ /opt/tuhengyu-panel/plugin/astrbot_plugin_tuhengyu/
    ```
    部署后**必须**核对：`grep -m1 '^version:'` 两份副本 + 容器内 `docker exec astrbot grep -m1 version /AstrBot/data/plugins/…/metadata.yaml`，三者一致才算落地。

12. **回复附带表情包（0.2.8）的边界**：走 `on_decorating_result` 钩子（**发送前**触发，可改 `event.get_result().chain`）。AstrBot 官方警告：**流式输出下依赖该钩子的插件可能不工作** —— 本机若开流式，表情包可能不生效。跨容器发图**必须 base64**（SnowLuma 与 AstrBot 是两个容器，文件系统不互通），实现见 `core/stickers.py::read_base64`。选图零 token、零 embedding：目录即标签 + 子串命中 + 随机。

13. **插件设置页读写自己的配置（0.2.9）**：由插件页面直接读写自身配置。后端读同级 `_conf_schema.json` 当渲染依据、读 `self.config`（`AstrBotConfig`，本质 dict）当当前值；写回走 `self.config.update(merged)` + `self.config.save_config()`，**只合并 schema 声明过的键**（防写坏配置）。
    - 下拉选项：人格 `await context.persona_manager.get_all_personas()`（**async**）；模型 `context.get_all_providers()`（**同步**，返回 `list[Provider]`）。
    - **`Provider` 没有 `provider_id` 属性** —— id 要从 `provider.meta().id` 取（`meta()` 同步；异常时回退 `provider.provider_config` 的 `id`）。用 `getattr(p, "provider_id")` 会静默拿到空串、下拉全空（本轮踩坑）。
    - 页面三页签用 `.tab` + `.tab-pane.active` 切换；设置分组用原生 `<details>/<summary>` 做可折叠，免 JS。

14. **插件页展示图片只能走 base64 + Pillow 缩略图（0.2.10 / 0.2.12）**：iframe 无 `allow-same-origin`，不能直接 `<img src>` 指后端文件路径；`GET /{插件名}/stickers` 把图读成 base64 内联返回（`read_base64`），前端拼 `data:<mime>;base64,…`。**直接内联原图不可行** —— 表情包往往 1～3MB，0.2.10 首版设 800KB 上限，博士的图直接显示「过大，未预览」。0.2.12 起改用 `thumb_b64()`（Pillow，320px，统一转 RGB 存 JPEG、透明填白底）生成缩略图，实测总响应 2.0MB → 405KB（降约 80%），GIF 单张 b64 由 16～21 万降到 3 万。后端仍留回退：缩略失败则小图内联原图（≤800KB），内联总量上限 24MB，超出标 `skipped`。插件页现有接口：`GET /status`、`POST /reschedule`、`POST /test-moment`、`POST /sticker-reload`、`GET /settings`、`POST /settings`、`GET /stickers`。

15. **表情包按情绪分类 & 单独发（0.2.13）**：情绪类目固定 6 类（开心 / 难过 / 生气 / 惊讶 / 无语 / 害羞，见 `core/emotion.py`）——博士要求「不需要太细分」。选图规则（零 token）：① 判 AI 本条回复文本的情绪，目录同名就取一张 → ② 标签名子串命中 → ③ default 散图 → ④ 全部随机。开关 `sticker.emotion_match`（默认开）可退回只看标签名。
    - **「单独发」用 `after_message_sent` 钩子**（`EventType.OnAfterMessageSentEvent`，回复发出后触发，见 `pipeline/respond/stage.py:328`），`await event.send(MessageChain([Image.fromBase64(b64)]))` 另发一条。与 `on_decorating_result` 的「一起发」靠 `sticker.send_separate`（默认关 = 一起发）分流，互斥不重复。概率 `sticker.probability`（默认 0.35）两条路径共用、设置页可调。
    - `page_stickers` 改用 `groups_by_emotion()`：目录名是情绪名的进对应类目，其余（default / collected / 自定义）归「其他」。item 带 `tag` 标出原始目录名。

16. **表情包 WebUI 新建分类 / 上传（0.2.14）**：分类 = `stickers/` 下的目录名；`groups_by_emotion()` 现在把**用户自建目录**各自独立成组，「default / collected」才归「其他」。后端 `POST /{插件名}/sticker-category`（body `{name}`）建目录、`POST /{插件名}/sticker-upload`（body `{category, filename, data}`，data 为 base64）存图；分类名禁 `/ \` 与 `.` 开头、≤20 字，单张 ≤8MB，按内容 md5 命名去重。前端上传用 `FileReader` 读成 base64 再 `bridge.apiPost`（iframe 无 allow-same-origin，不用表单上传）。`GET /stickers` 新增返回 `categories`（真实目录名，供上传下拉）。

### 插件设计决策（2026-10-01 定，代码未动）

**作息跟人设走**（不硬编码）：

- 我原草案拟了一套「上班族作息」当默认，**是错的** —— 示例人设「夜班便利店店员」白天该睡、凌晨才是主场。
- 且项目定位就是「人设驱动」，作息硬编码等于把最像生活的部分摘出去。
- 机制：首次启动读人设 → 问模型生成日程 JSON → **存盘**；之后直接读盘（不烧 token）；
  人设改了按指纹重算；**空人设 / 失败 → 保守默认**（活跃时段短、动作少）。
- 「作息存盘」与「调度状态落盘」是同一套机制，一起做。

**私聊与群聊分四层表现**：

| 层 | 私聊 | 群聊 | 归谁 |
|---|---|---|---|
| 该不该回 | 就该回 | 被 @ 必回；没 @ 要掂量 | 框架 + 插件加判断 |
| 语气 | 近、松 | 收、有分寸 | 人设 + 注入场景说明 |
| 长度 | 可长 | 短 | 同上 |
| 主动性 | 基本不主动 | 低概率插一句 | **插件纯新增** |

**下一步（先核实再动手）**：核实 AstrBot 插件 API 三条 —— ① 能否取到私聊/群聊标志
② 能否修改 system prompt ③ 能否在回复前拦截。产出「能做 / 不能做 / 要绕」清单后
再定第一版做几层。

### 插件第一版（2026-10-01 打通）

**发空间不再阻塞。** `_post_moment()` 从 `return False` 变成一条真实可用的路径：

```
OneBot get_cookies(domain="user.qzone.qq.com")
  → p_skey → bkn() → g_tk
  → POST emotion_cgi_publish_v6（14 字段）
  → code:0
```

**实测证据**：QQ 里发 `/图恒宇测试`，机器人回了

> [图恒宇] 已发布：刚下班路上看到天边一片橘红色的晚霞，好看得站在原地看了好一会儿，突然觉得今天也没那么累了

同一条内容出现在 QQ 空间。

**两个致命细节**（踩坑记录）：

| 坑 | 现象 | 正解 |
|---|---|---|
| 取 cookie 不带 `domain` | `code:-3000 请先登录空间` | 必须 `domain="user.qzone.qq.com"` |
| g_tk 用 `get_csrf_token` | 同样 -3000 | g_tk 必须由 `p_skey` 经 **bkn** 算 |

**插件代码在 `plugin/astrbot_plugin_tuhengyu/`**，已随仓库分发（Gitee + GitHub）。
安装：`cp -r plugin/astrbot_plugin_tuhengyu <AstrBot数据目录>/plugins/ && docker restart astrbot`。

**行动机制**：调度器按「活跃时段 + 检查间隔（30 min）+ 触发概率（15%）」决定何时行动；发空间另有 6 小时最短间隔。内容由 AstrBot 里配的模型生成（无需另配 key）。

### 面板打磨（2026-10-01，**已搁置**）

面板从「能用」推到「好用」的一轮，末次 commit `ec3cce1`。**用户决定暂时搁置此处，转入插件开发。**

| 项 | 内容 |
|---|---|
| 读取初始凭据 | 折叠区一键读出 noVNC / AstrBot / SnowLuma 的初始密码。三处来源均已实测：**noVNC 在容器环境变量 `VNC_PASSWD`**（不在日志里），另两个在启动日志 |
| v0.3 界面 | 深色 + 青紫渐变、手机响应式、凭据表格化、自绘内联 SVG 素材（**不能用外链** —— 目标机无国际出口，CDN 一律加载不出来） |
| 安全默认 | 面板不再可能「无密码裸跑」：环境变量 → `.panel_pass` 文件 → 内存随机值，三级回退 |
| 自建登录页 | 弃用 HTTP Basic Auth（浏览器原生弹窗样式完全不可控），改 HMAC 签名会话 Cookie。**关键**：NiceGUI 的 socket.io 真实挂载点是 `/_nicegui_ws/`，与 `/_nicegui/` 前缀**互不匹配**，必须单独拦 |
| 入场动画 | 从透明「实体化」（opacity + blur 收实），1.2s |
| 毛玻璃 | 步骤按钮 + 复制按钮用 `backdrop-filter`；配套给 body 加背景光斑 —— **纯色背景上毛玻璃看不出效果** |
| 预置插件 | 「④ 安装 AstrBot」自动把配套插件放进 `./data/plugins/`；另有独立的 **「⑥ 装配套插件」** 按钮，对已装好的机器也能补装/重装。commit `af4b985` |

**踩过的坑（动画前后改了四版，详见 `logs/2026-10-01-面板登录页.md`）**：

1. 面板是**客户端渲染** —— 初始 HTML 里只有一个 `<div id="app">`，`grep` 到的 class 全在 CSS 里、不是真实 DOM。
2. **真凶**：三代代码都写了 `@media (prefers-reduced-motion: reduce)`，用户系统开着「减弱动态效果」→ 动画被整个关掉。这是「怎么改都看不到」的统一解释。
3. 教训：**动手前先花一次查询确认「HTML 是 SSR 还是 CSR」**，能省三轮返工。

### 端到端验收（2026-10-01，决定性证据）

真人从 QQ 发「在吗」，机器人应答「在的！有什么可以帮你的吗？😊」：

```
14:42:57  AstrBot   [default(aiocqhttp)] 2664648140: 在吗
14:43:01  AstrBot   Prepare to send - /2664648140: 在的！有什么可以帮你的吗？😊
14:42:57  SnowLuma  [Event] 私聊 2664648140: 在吗
14:43:01  SnowLuma  [OneBot] 私聊 2664648140 | 发送：在的！有什么可以帮你的吗？😊
```

**对话模型**：LongCat-2.5-Preview，`api_base = https://api.longcat.chat/openai/v1`。
⚠️ 该模型是**推理模型**，`max_tokens` 配小会导致 `content` 为空（token 被 `reasoning_content` 吃掉）。

**无国际出口的实际影响**（教程必写）：
- 可用 API 仅国内：DeepSeek ✅ / 通义 ✅ / 硅基流动 ✅；智谱 ❌ / Kimi ❌ / OpenAI ❌
- **AstrBot 插件市场不可用**（走 `api.soulter.top` 与 GitHub）→ 插件须手动安装

### 验证机（一次性，可随时重建）

| 项 | 值 |
|---|---|
| 面板 | `http://183.66.27.21:50505` admin / Tuhengyu2026 |
| SnowLuma WebUI | `http://183.66.27.21:50507` |
| noVNC | `http://183.66.27.21:50506` 密码 `tuhengyu2026` |
| AstrBot WebUI | `http://183.66.27.21:43211`（公网映射 → 宿主 6185）astrbot / `Nrvn5CCJ9P9rAR3ghsgDbg1b` —— 2026-10-01 用宿主 `6185` 直调登录 API 返回 **401**，密码疑似已改，待核 |
| SSH | `root@183.66.27.21:53923` |

### 未决事项

- [ ] AstrBot / SnowLuma 改密（验证机暴露公网）
- [ ] 面板自身 LICENSE（本项目原创部分许可方式未定）
- [ ] 插件发空间接口（`_post_moment()` 仍是占位，需确认走协议端扩展还是空间 Web 接口）
- [ ] 仓库范围：目前 `git` 仓库只含 `panel/`，**README / logs / plugin / scripts / refs 未纳入**，是否要合并成单仓待定
- [ ] 面板是否内置「离线镜像导入」入口（应对无国际出口的机器）

### 关键教训（写教程时必须带上）

1. **租机器前先验 `docker pull`** —— 无国际出口的国内 VPS 拉不了 Docker Hub 镜像，会在第③步卡死。
2. **官方脚本有 bug** —— snap 误判、跳过本地镜像，见 `panel/vendor/apply_patches.py`。
3. **GitHub 全系不可达** —— 分发必须走 Gitee，实测可用。

## 工作规则（参照，非继承）

- 覆盖既有文件前先备份至 `archive/`。
- 版本文件用数字后缀，不用 `latest` 之类易错拼写。
- 资料不足处标「资料不足」，不猜测、不补全。
