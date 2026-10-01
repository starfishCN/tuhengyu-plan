# 第三方内容声明（NOTICE）

本目录（`vendor/`）包含**非本项目原创**的第三方脚本。声明如下。

---

## 文件清单

| 文件 | 来源 | 性质 |
|---|---|---|
| `snowluma_install.sh` | SnowLuma 官方部署脚本 | 第三方，**非商业许可** |
| `apply_patches.py` | 本项目原创 | 见文末「本项目自身许可」 |

### `snowluma_install.sh`

- **原始来源**：`https://github.com/SnowLuma/SnowLuma.Docker.Framework`
- **原始地址**：`https://raw.githubusercontent.com/SnowLuma/SnowLuma.Docker.Framework/main/install.sh`
- **抓取日期**：2026-10-01
- **原始字节数**：33,011（抓取时） / 37,261（本仓库内，含下方补丁）
- **许可**：SnowLuma 采用「**源码可见、非商业**」许可（非 OSI 开源许可）。著作权归 SnowLuma 原作者所有。

#### 本项目的改动（补丁）

仅两处，均由 `apply_patches.py` 记录，便于上游更新后重打：

| # | 位置 | 改动 |
|---|---|---|
| P1 | `install_docker_engine` 的 snap 检测 | 删除 `docker info \| grep -qi 'snap'` 的宽泛匹配（会误判 Docker 29.x 的 `io.containerd.snapshotter.v1`），只保留 `/snap/` 路径判断 |
| P2 | `pull_image` | pull 前增加 `docker image inspect "${IMAGE}" >/dev/null 2>&1 && return 0` 短路，跳过已存在镜像 |

#### 分发声明

- 本项目将其**原样保留并内置**，唯一目的是**规避国内网络无法访问 GitHub 的部署障碍**（实测国内加速源全部不可用）。
- 本项目的使用场景为**非商业**的教程与个人部署。
- 本项目**不主张对该脚本的任何权利**，**不声称获得原作者授权**，该脚本的一切权利归 SnowLuma 原作者所有。
- 若原作者对本项目的内置分发有异议，**一经提出即行移除或改为其他方案**。
- 建议使用者以官方仓库为最终权威来源。

---

## 本项目自身许可

本项目原创部分（面板代码、教程、配套插件）的许可方式**待定**（见 README「待定项」）。
