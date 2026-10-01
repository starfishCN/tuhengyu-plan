# 图恒宇计划 · 插件

给 bot「完整的一生」。第一版：**作息 + 调度器 + 发 QQ 空间**。

- 包名：`astrbot_plugin_tuhengyu`
- 版本：0.2.2
- 支持平台：`aiocqhttp`（OneBot v11）
- 许可：待定（见项目 README）

## 它做什么

调度器按「作息 + 检查间隔 + 概率」决定何时行动。作息**跟人设走**：
首次启动读人设，让模型推一份一天的作息存盘，之后只读盘（不烧 token）。
空人设或生成失败 → 保守默认（09:00–23:00 醒）。

每次行动时：

1. 看此刻在干嘛（作息给的 scene / state）
2. 按状态给触发概率加权（在忙少动，闲着多动）
3. 用 AstrBot 里配好的模型生成一条说说内容（**带上「此刻」**，所以发的不是凭空的话）
4. 通过 OneBot 向协议端要 QQ 空间 cookie，算 g_tk，POST 到空间接口

**不需要你额外配模型 key** —— 直接用 AstrBot 的。

## 安装

AstrBot 插件市场在**无国际出口的机器上不可用**，所以手动装：

```bash
# 1. 取代码（仓库根目录下有 plugin/ 文件夹）
git clone https://gitee.com/starfishCN/tuhengyu-plan.git
# 2. 放进插件目录（宿主机上就是 AstrBot 的 data/plugins/）
cp -r tuhengyu-plan/plugin/astrbot_plugin_tuhengyu <AstrBot数据目录>/plugins/
# 3. 重启 AstrBot
docker restart astrbot
```

启动成功的话，日志里会出现：

```
Plugin astrbot_plugin_tuhengyu (0.2.0) by starfishCN
[图恒宇] 生活调度器已启动。
```

## 命令

| 命令 | 作用 |
|---|---|
| `/图恒宇` | 看调度器状态（作息、间隔、概率、上次发空间时间） |
| `/图恒宇测试` | **立刻**生成并发布一条，用于验证链路 |

## 配置

在 AstrBot WebUI 的插件配置页改。配置按分组折叠：

| 分组 | 键 | 说明 | 默认 |
|---|---|---|---|
| — | `enabled` | 总开关 | `true` |
| — | `persona_prompt` | **人设** —— 告诉它「你是谁」，作息和说说内容都由它决定 | 空 |
| `chat_private` | `enabled` / `prompt` / `model` | 私聊场景说明与模型 | 开 |
| `chat_group` | `enabled` / `prompt` / `model` | 群聊场景说明与模型 | 开 |
| `schedule` | `auto_generate` | 按人设自动生成作息 | `true` |
| `schedule` | `manual_hours` | 手动作息，如 `09:00-23:00`（关自动生成时生效） | `09:00-23:00` |
| `schedule` | `generate_model` | 生成作息用的模型，留空用 AstrBot 当前默认 | 空 |
| `scheduler` | `check_interval_minutes` | 调度器多久检查一次 | `30` |
| `scheduler` | `act_probability` | 每次检查触发行动的**基础**概率 | `0.15` |
| `scheduler` | `state_bias` | 按此刻状态加权（忙 0.35 倍 / 闲 1.6 倍，封顶 0.9） | `true` |
| `moment` | `enabled` | 是否允许发空间 | `true` |
| `moment` | `min_interval_hours` | 两次发空间的最小间隔（小时） | `6` |
| `moment` | `prompt` | 发说说时给模型的指令 | 空 |
| `moment` | `provider_id` | 生成说说内容的模型，留空用 AstrBot 当前默认 | 空 |

> ⚠️ 这些是**嵌套键**（`schedule.manual_hours` 这种），不是扁平 key。
> 0.2.0 之前的旧配置名（`active_hours` / `moment_enabled` 等）已废弃，需重填一次。

### 人设怎么填

`persona_prompt` 就是角色的「底色」。比如：

```
你是「小夜」，一个话不多的夜班便利店店员。说话短，偶尔冷幽默，
喜欢观察来店里的客人，不爱用感叹号。你发动态是为了记录，不是为了营业。
```

留空的话，插件会用内置的通用口吻（一个普通人随手记心情）。

## 原理备注（给好奇的人）

**为什么不能直接用 OneBot 发空间？**
OneBot v11 标准协议里没有这个动作，SnowLuma / NapCat 也都没提供。所以只能直连 QQ 空间的 Web 接口。

**cookie 从哪来？**
QQ 客户端登录态就在协议端里，`get_cookies` 动作能把它吐出来。
⚠️ 必须带 `domain` 参数（如 `user.qzone.qq.com`），否则拿到的 cookie 不在空间域上，会被判「请先登录空间」。

**g_tk 是什么？**
空间接口的 CSRF 防护，由 cookie 里的 `p_skey` 经 bkn 算法算出（不是 `get_csrf_token`）。

## 风险

- 空间接口是**逆向**的，官方随时可能改，改了就会失效。
- **主动行为是非官方 bot 的高危区**。默认参数已经比较克制（6 小时间隔 + 15% 概率），别调得太激进。

## 未实现（后续）

- 发表情包
- 主动发言（私聊/群聊的第一句话）
- 怼人时机
- 作息改动后自动重算已有内存副本（现在人设变了要重启插件才重读）

## 已知问题

- 调度器的「上次发空间时间」存在内存里，**重启 AstrBot 会丢**，可能刚重启就补发一条。后续要落盘。
