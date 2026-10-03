# Gitee raw 451 未因改名解决 —— 一键命令改走 jsDelivr

日期：2026-10-03
状态：已实测 / 教程与 README 已改 / 已推公开仓
关联：`panel/setup.sh`、`tutorial/02`、`tutorial/09`、`README-repo.md`

## 背景

上一台设备把 `install.sh` 改名 `setup.sh`，理由是 Gitee 风控只命中 `install.sh`（raw 451）。本次复测，**改名没有解决问题**。

## 实测（2026-10-03，本机直连）

| 目标 | 结果 |
|---|---|
| Gitee raw `/raw/main/setup.sh` | **HTTP 451** |
| Gitee raw `/raw/main/install.sh` | HTTP 404（文件已删） |
| Gitee raw `/raw/main/README.md` | 200（4323 B） |
| Gitee raw `/raw/main/main.py` | 200（38443 B） |
| Gitee API `contents/setup.sh` | 200（4522 B） |
| jsDelivr `gh/.../setup.sh@main` | 200（4522 B） |
| GitHub raw `.../main/setup.sh` | 200（4522 B） |

**结论**：451 与文件名无关，指向 `.sh` 内容/扩展本身；Gitee 仓库内其他文件正常。改名规避无效。

## 处置

一键命令主源改为 **jsDelivr**（镜像 GitHub，国内多数可达）：

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/starfishCN/tuhengyu-plan@main/setup.sh | bash
```

同步改动：
- `tutorial/02-装部署面板.md`：命令行 + 「成功的样子」输出块（对齐当前 `setup.sh` 的收尾文案）。
- `README-repo.md`：命令行。
- `README.md`（私有）：命令行。
- `tutorial/09-常见问题.md`：新增「一键命令拉不下脚本（curl 报 451 / 空内容）」，给三级备用：jsDelivr → GitHub raw → Gitee API 取文件。

## 公开仓

发布仓 Gitee + GitHub 已同步至 `6e56d47`（含 `setup.sh` 改名、随机初始密码、venv 兜底、教程与日志）。发布前凭据扫描：**本次新增文件 0 命中**。

## 遗留

- 旧日志（`logs/2026-10-01-*`、`2026-10-02-*`）中仍含验证机 IP/端口/明文口令，且**早已在公开仓**。用户此前口径为「不动」；另一台设备已开始对新增日志脱敏。是否回扫历史待定。
- Gitee 仓库 `raw` 对 `.sh` 的 451 仍存在，若要彻底解决需转 Gitee 工单，或把脚本托管到 GitHub/jsDelivr 为主入口。