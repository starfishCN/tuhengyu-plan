# 图恒宇计划 · 插件

给 bot「完整的一生」。让人设不只是「会说话」，而是**有自己的作息、会自己发空间、会发表情包、会怼人、偶尔在群里插一句**。

- 包名：`astrbot_plugin_tuhengyu`
- 版本：0.3.4
- 支持平台：`aiocqhttp`（OneBot v11）
- 许可：待定（见项目 README）

## 它做什么

六项行为，一个插件，**全部由人设驱动** —— 换一份人设，作息和说话方式跟着变。

| # | 行为 | 说明 | 零 token？ |
|---|---|---|---|
| 1 | **作息 + 虚拟行动** | 首次启动读人设，问模型推一份一天的作息存盘；之后按作息决定「此刻在干嘛」，并据此加权行动概率 | 生成时一次 |
| 2 | **发 QQ 空间** | 按作息生成一条说说并发布（直连空间 Web 接口） | 否 |
| 3 | **表情包** | 回复时按概率附一张图；可按 AI 的意图选图；也可单独发；自动收集别人发的图 | 选图零 token |
| 4 | **好感度** | 自研三维状态（好感 / 印象 / 关系），注入对话并在回复末尾回收；语气随区间变化 | 否 |
| 5 | **戳一戳** | 被戳时按人设 + 好感度反应：冷却内不理、连戳怼回、关系好回戳并说话 | 可关 |
| 6 | **群聊主动插话** | 醒着时极低概率在群里接一句，接最近的群聊 | 否 |

调度器按「作息 + 检查间隔 + 概率」决定何时行动，所有后台行为都依赖它 —— 否则会出现凌晨三点发自拍这种事。

**不需要你额外配模型 key** —— 直接用 AstrBot 里配好的模型。

## 安装

### 推荐：用面板一键部署

本插件是「图恒宇计划」的一部分，配套部署面板会一并装好 AstrBot 与本插件。零基础用户走这条，不用敲命令。见项目根目录 README。

### 手动安装（进阶 / 备用）

AstrBot 插件市场在**无国际出口的机器上不可用**，所以手动装：

```bash
# 1. 取代码（仓库根目录下有 plugin/ 文件夹）
git clone https://gitee.com/starfishCN/tuhengyu-plan.git
# 2. 放进插件目录。Docker 部署的 AstrBot，数据目录通常就是 /AstrBot/data/
cp -r tuhengyu-plan/plugin/astrbot_plugin_tuhengyu <AstrBot数据目录>/plugins/
# 3. 重启 AstrBot
docker restart astrbot
```

> 找不到数据目录时：它就是你给 AstrBot 挂载的那个卷。官方镜像默认在容器内 `/AstrBot/data/`，
> 宿主机上一般是 `./data` 或某个具名卷。`plugins/` 就在它下面。

启动成功的话，日志里会出现：

```
Plugin astrbot_plugin_tuhengyu (0.3.1) by starfishCN
[图恒宇] 生活调度器已启动。
```

## 命令

| 命令 | 作用 |
|---|---|
| `/图恒宇` | 看调度器状态（作息、间隔、概率、上次发空间时间） |
| `/图恒宇测试` | **立刻**生成并发布一条空间动态，用于验证链路 |
| `/图恒宇插话 群号` | 手动让它在指定群插一句（调试用，不需要开主动插话开关） |
| `/图恒宇好感` | 看当前会话的好感度三维状态 |
| `/token诊断` | 输出本次会话的 system prompt / 上下文 / 工具字符量与折算 token |

## 插件页面（WebUI 内）

在 WebUI 的插件详情页里有一页「运行状态」（`pages/status/`），四个页签，不用敲命令：

- **状态**：此刻状态、醒着/睡着、作息来源与段数、当前人设、触发概率（基准 × 状态倍数）、检查间隔、发空间开关、上次发空间时间、作息时段表（当前命中的一行高亮）
- **操作**：重算作息 / 测试发一条空间动态（二次确认）/ 重扫表情包目录
- **设置**：直接读写插件配置（与 AstrBot 官方设置页是同一份），下拉可选人格与模型
- **表情包**：按分类浏览、新建分类、上传图片、一键「自动归类」（调多模态模型把散图归入意图类目）；也能把任意一张卡片**手动拖进**别的分类归类（纯文件移动，零 token）。拖动只是暂存（卡片打「待保存」标记），点**「保存归类」**才一次提交、只刷新一次；空分类会保留落点，可随时拖回

页面后端 API 由插件自己注册（路由带插件名前缀）：

| 方法 | 路由 | 作用 |
|---|---|---|
| GET | `/astrbot_plugin_tuhengyu/status` | 结构化运行状态 |
| POST | `/astrbot_plugin_tuhengyu/reschedule` | 丢弃旧作息并按人设重新生成 |
| POST | `/astrbot_plugin_tuhengyu/test-moment` | 立即生成并发布一条空间动态 |
| POST | `/astrbot_plugin_tuhengyu/sticker-reload` | 重扫表情包目录 |
| GET | `/astrbot_plugin_tuhengyu/stickers` | 表情包库（含缩略图） |
| POST | `/astrbot_plugin_tuhengyu/sticker-category` | 新建分类 |
| POST | `/astrbot_plugin_tuhengyu/sticker-upload` | 上传图片（base64） |
| POST | `/astrbot_plugin_tuhengyu/sticker-classify` | 识图归类（按批） |
| POST | `/astrbot_plugin_tuhengyu/sticker-move` | 手动把一张图移到别的分类（拖拽；前端暂存后批量提交） |
| GET | `/astrbot_plugin_tuhengyu/settings` | 配置 schema + 当前值 + 下拉选项 |
| POST | `/astrbot_plugin_tuhengyu/settings` | 保存配置 |

改页面静态文件刷新页面即可；新增或删除页面目录要重载插件。

## 配置

在 AstrBot WebUI 的插件配置页改（或用本插件的「设置」页签）。配置按分组折叠：

| 分组 | 键 | 说明 | 默认 |
|---|---|---|---|
| — | `enabled` | 总开关 | `true` |
| — | `persona_id` | **人格** —— 下拉选 AstrBot 已配置的人格。**留空 = 跟随 AstrBot 当前默认人格** | 空 |
| — | `persona_prompt` | 人设补充（可选），追加在所选人格后面 | 空 |
| `chat_private` | `enabled` / `prompt` / `model` | 私聊场景说明与模型 | 开 |
| `chat_group` | `enabled` / `prompt` / `model` | 群聊场景说明与模型 | 开 |
| `schedule` | `auto_generate` | 按人设自动生成作息 | `true` |
| `schedule` | `manual_hours` | 手动作息，如 `09:00-23:00` | `09:00-23:00` |
| `schedule` | `generate_model` | 生成作息用的模型，留空用默认 | 空 |
| `scheduler` | `check_interval_minutes` | 调度器多久检查一次（分钟） | `30` |
| `scheduler` | `act_probability` | 每次检查触发行动的**基础**概率 | `0.15` |
| `scheduler` | `state_bias` | 按此刻状态加权 | `true` |
| `scheduler` | `bias_busy_factor` / `bias_idle_factor` | 「在忙」/「闲着」的概率倍数 | `0.35` / `1.6` |
| `scheduler` | `bias_busy_keywords` / `bias_idle_keywords` | 状态判定关键词，留空用内置 | 空 |
| `moment` | `enabled` | 是否允许发空间 | `true` |
| `moment` | `min_interval_hours` | 两次发空间的最小间隔（小时） | `6` |
| `moment` | `prompt` / `provider_id` | 说说指令与生成模型 | 空 |
| `sticker` | `enabled` | 回复是否附带表情包 | `true` |
| `sticker` | `probability` | 每条回复附图的概率 | `0.35` |
| `sticker` | `intent_match` | 按 AI 的意图挑图 | `true` |
| `sticker` | `send_separate` | 附图单独发一条 | `false` |
| `sticker` | `collect_enabled` | 自动收集对话里的图片 | `true` |
| `sticker` | `collect_label` | 收集来的图放进哪个目录 | `collected` |
| `sticker` | `classify_model` | 识图归类用的模型（需支持多模态），留空用默认 | 空 |
| `favour` | `enabled` / `inject` / `session_based` | 好感度开关、注入开关、是否按会话独立 | `true`/`true`/`false` |
| `poke` | `enabled` / `use_model` / `cooldown_seconds` / `repeat_window_seconds` / `snap_threshold` / `poke_back_prob` / `speak_prob` / `model` | 戳一戳各项 | 见设置页 |
| `proactive` | `enabled` | 主动插话总开关（**默认关**） | `false` |
| `proactive` | `probability` / `hot_window_minutes` / `min_recent_messages` / `cooldown_minutes` / `daily_cap_per_group` / `max_chars` / `groups` / `model` | 插话各项 | 见设置页 |

> ⚠️ 这些是**嵌套键**（`schedule.manual_hours` 这种），不是扁平 key。
> 0.2.0 之前的旧配置名（`active_hours` / `moment_enabled` 等）已废弃，需重填一次。

### 人设怎么填

**不用在插件里抄一份。** 插件直接读 AstrBot 的「人格」：

1. 在 AstrBot WebUI 里把人格配好；
2. 插件配置里的 `persona_id` **留空**，即跟随 AstrBot 当前默认人格；
3. 想给这个插件单独指定另一个，就在 `persona_id` 的下拉里挑一个。

少数情况下需要在人格之外再加一段说明，才填 `persona_prompt`。都没配的话，插件用内置的通用口吻。

## 代码结构（0.3.0 起）

`main.py` 只留生命周期、公共辅助与注册；业务按职责拆成 mixin，主类多继承组装。改一个行为只需开一个文件。

| 文件 | 类 | 内容 |
|---|---|---|
| `main.py` | `TuhengyuPlugin` | `__init__`（含 11 个 Web 路由注册）/ `initialize` / `terminate` / `_refresh_persona` / `_data_dir` / `_data_file` / `_sec` |
| `handlers/sticker.py` | `StickerHandlers` | 附图、单独发、收集 |
| `handlers/favour.py` | `FavourHandlers` | 好感度注入与回收 |
| `handlers/poke.py` | `PokeHandlers` | 戳一戳判定、文本、回戳 |
| `handlers/proactive.py` | `ProactiveHandlers` | 群聊观察、插话判定、状态落盘 |
| `commands.py` | `CommandHandlers` | 5 个聊天命令 |
| `web/routes.py` | `WebRoutes` | 11 个页面 API |
| `web/settings.py` | `SettingsHandlers` | 设置 schema / 取值 / 回落 / 合并 |
| `diag/token.py` | `TokenHandlers` | token 估算、快照、输出 |

拆法依据 AstrBot 的注册机制：`@filter.*` 装饰器在**模块导入时**注册，`handler_module_path` 取模块名，卸载按 `data.plugins.<插件目录>` 前缀清理 —— 所以把带装饰器的方法放子模块、由主类继承，注册与卸载行为都与单文件时一致。

> 自己加方法时注意相对导入：子目录文件用 `from ..core.x`，根目录文件（`main.py`、`commands.py`）用 `from .core.x`。

## 原理备注（给好奇的人）

**为什么不能直接用 OneBot 发空间？**
OneBot v11 标准协议里没有这个动作，SnowLuma / NapCat 也都没提供。所以只能直连 QQ 空间的 Web 接口。

**cookie 从哪来？**
QQ 客户端登录态就在协议端里，`get_cookies` 动作能把它吐出来。
⚠️ 必须带 `domain` 参数（如 `user.qzone.qq.com`），否则拿到的 cookie 不在空间域上，会被判「请先登录空间」。

**g_tk 是什么？**
空间接口的 CSRF 防护，由 cookie 里的 `p_skey` 经 bkn 算法算出（不是 `get_csrf_token`）。

**人设怎么进模型？**
长人设拼进 user 消息（不是 system），并且会用一句硬要求点名人设，避免被具体任务盖过 —— 详见 `core/proactive.py` 与 `core/persona.py` 的注释。

## 风险

- 空间接口是**逆向**的，官方随时可能改，改了就会失效。
- **主动行为（发空间 / 主动插话 / 回戳）是非官方 bot 的高危区**。默认参数已比较克制（发空间 6 小时间隔 + 15% 概率；插话默认关闭），别调得太激进。
- 不要把 noVNC / WebUI / OneBot 端口裸暴露在公网（官方警告）。

## 已知问题

- 调度器的「上次发空间时间」存在内存里，**重启 AstrBot 会丢**，可能刚重启就补发一条。后续要落盘。
- 群聊记录只存内存，重启即清空（`proactive.json` 只存冷却与计数）。