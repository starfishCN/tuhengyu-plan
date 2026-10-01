# 表情包目录

放图即可，不用改代码、不用接向量库。

## 怎么放

```
assets/stickers/开心/a.png      → 标签 = 开心
assets/stickers/无语/b.jpg      → 标签 = 无语
assets/stickers/c.png           → 标签 = default（散图）
```

- **子目录名就是标签**。标签名写词面直白的词（开心 / 困 / 无语 / 摸鱼…），命中率才高。
- 直接丢在 `stickers/` 根下的图归 `default`，谁都没命中时发它们。
- 支持的扩展名：png / jpg / jpeg / gif / webp / bmp。

## 怎么选图（零 token，零 embedding）

bot 每次回复时：

1. 拼出「此刻的作息场景 + 心情 + 本条回复正文」这段文本；
2. 看里面**是否出现某个标签名**（子串命中）→ 命中就从这个标签里随机发一张；
3. 没命中 → 发 `default` 里的散图；
4. 连 `default` 也没有 → 从全部图里随机一张；
5. 一张图都没有 → 不发。

## 放哪

**推荐**：放进插件数据目录的 `stickers/`：

```
<AstrBot数据目录>/plugin_data/astrbot_plugin_tuhengyu/stickers/
```

那儿的图不会随插件更新丢失。放在本目录（插件内置）的图作为随插件分发的默认素材，
升级插件时会被覆盖 —— 自己的图放数据目录。

放完图后，在插件页点「重扫表情包」即可生效，不必重载插件。
