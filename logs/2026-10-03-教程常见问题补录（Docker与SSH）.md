# 2026-10-03 · 教程常见问题补录（Docker 与 SSH）

## 缘由

带人实测走教程第一、二步时踩到一批新坑，全部补进 `tutorial/09-常见问题.md`。
面向读者，不含任何机器信息、IP、凭据。

## 实测记录

### Docker 安装与镜像源

| 项 | 结果 |
|---|---|
| `docker.io`（Ubuntu 源） | 安装成功，版本 29.1.3 |
| 顺序坑 | 先写 `daemon.json` 后装 Docker，配置文件不报错但无效，必须重启 docker 才读 |
| Docker Hub 直连探测 | 目标机 `000`（不通）；对照机 `200` |
| `docker.m.daocloud.io` | 入口 401 通 |
| `docker.m.daocloud.io` 的 blob | 走 Cloudflare R2，超时 |
| `docker.1ms.run` | 入口 401 通 |
| `docker.1ms.run` 的 blob | 走 Cloudflare，超时 |
| `docker.xuanyuan.me` | `000` 已死 |

### 结论：入口通 ≠ 能拉

加速器的 registry 入口在国内可达（回 401），
但大文件 blob 托管在境外 Cloudflare，NAT 型无国际出口的机器一律超时。
**换源解决不了**，只能换机器 / 挂代理 / 手动中转。

### SSH 报错分类

实测收敛为四类：`Bad port`（端口含非法字符）、
`Could not resolve hostname`（地址不合法，常见于混入中文标点或把掩码一起复制）、
`Connection timed out`（映射未开）、
`Permission denied`（网络已通、仅凭据错）。

## 动作

- `tutorial/09-常见问题.md` 新增 6 节：装 Docker 顺序 / 两条探测命令与判读表 /
  三步配加速 / 入口通但本体拉不动的坑 / SSH 报错对号表；净增 105 行。
- 未新增文件，教程篇目表不变。

## 遗留

- 「有国际出口的线路」如何在租机器前验证 —— 01 篇已有 curl 命令，可考虑与本节互链。
- 手动中转（`docker save` / `load`）流程教程未写，若读者踩到再补。
