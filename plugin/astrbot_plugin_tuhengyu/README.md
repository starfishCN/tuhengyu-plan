# 图恒宇计划 · 插件

给 bot「完整的一生」。第一版：**作息 + 调度器 + 发 QQ 空间**。

- 包名：`astrbot_plugin_tuhengyu`
- 版本：0.2.0
- 支持平台：`aiocqhttp`（OneBot v11）
- 许可：待定（见项目 README）

## 它做什么

调度器按「作息 + 检查间隔 + 概率」决定何时行动。每次行动时：

1. 用 AstrBot 里配好的模型生成一条说说内容
2. 通过 OneBot 向协议端要 QQ 空间 cookie
3. 算 g_tk，POST 到空间接口
4. 发出去

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

在 AstrBot WebUI 的插件配置页改：

| 键 | 说明 | 默认 |
|---|---|---|
| `enabled` | 总开关 | `true` |
| `active_hours` | 活跃时段，如 `09:00-23:00`；多段用英文逗号分隔 | `09:00-23:00` |
| `check_interval_minutes` | 调度器多久检查一次 | `30` |
| `act_probability` | 每次检查触发行动的概率 | `0.15` |
| `moment_enabled` | 是否允许发空间 | `true` |
| `moment_min_interval_hours` | 两次发空间的最小间隔（小时） | `6` |
| `llm_provider_id` | 用哪个模型生成内容，留空用 AstrBot 当前默认 | 空 |
| `persona_prompt` | **人设** —— 告诉它「你是谁」，想让它像某个角色就写在这 | 空 |
| `moment_prompt` | 发说说时给模型的指令 | 空 |

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
- 更像人的作息（现在是固定时段 + 随机）

## 已知问题

- 调度器的「上次发空间时间」存在内存里，**重启 AstrBot 会丢**，可能刚重启就补发一条。后续要落盘。
