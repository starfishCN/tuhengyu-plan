"""表情包：按标签挑一张图 —— 不接 embedding，不接向量库。

约定（目录即标签）：
    assets/stickers/<标签>/xxx.png     → 标签 = 子目录名
    assets/stickers/xxx.png            → 标签 = default（散图）

选图优先级（prefer_emotion=True 时）：
    ① 先按「AI 此刻的情绪」定位目录 —— 用 core/emotion.py 的关键词规则，
       从传入文本里判出情绪类目（开心/难过/…），目录同名就随机取一张
    ② 否则标签名出现在文本里 → 该标签随机一张
    ③ 再否则用 default 标签（散图）
    ④ 再否则从全部里随机
    ⑤ 一张图都没有 → None

“匹配”就是子串命中，确定性、零成本。标签命名尽量用词面直白的词
（开心 / 困 / 无语 / 摸鱼…），命中率就高。要更聪明可在上层加一次
模型选标签，但默认不做 —— 保持零 token。
"""
from __future__ import annotations

import hashlib
import logging
import random
from pathlib import Path

from .emotion import FALLBACK as EMOTION_FALLBACK
from .emotion import detect as detect_emotion
from .emotion import labels as emotion_labels

logger = logging.getLogger("astrbot")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
DEFAULT_LABEL = "default"


class StickerLibrary:
    """本地表情包库。只做「扫目录 + 挑一张」。"""

    def __init__(self, roots):
        if isinstance(roots, (str, Path)):
            roots = [roots]
        self.roots = [Path(r) for r in roots]
        self._index: dict[str, list[Path]] = {}
        self.reload()

    # ---------- 扫描 ----------
    def reload(self) -> None:
        """重新扫描目录。新增/删除表情包后可调（或重载插件）。"""
        index: dict[str, list[Path]] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                    continue
                rel = p.relative_to(root)
                label = rel.parts[0] if len(rel.parts) > 1 else DEFAULT_LABEL
                index.setdefault(label, []).append(p)
        self._index = index

    # ---------- 查询 ----------
    def has_any(self) -> bool:
        return bool(self._index)

    def count(self) -> int:
        return sum(len(v) for v in self._index.values())

    def labels(self) -> list[str]:
        return sorted(self._index)

    def describe(self) -> str:
        """给状态页用的一行摘要。"""
        if not self._index:
            return "无（把图放进 stickers/ 即可）"
        parts = [f"{lab}×{len(self._index[lab])}" for lab in self.labels()]
        return f"共 {self.count()} 张 · " + " / ".join(parts)

    def groups(self) -> dict[str, list[Path]]:
        """按标签分组返回副本（供页面展示，外部改动不影响索引）。"""
        return {lab: list(paths) for lab, paths in self._index.items()}

    def groups_by_emotion(self) -> dict[str, list[tuple[str, Path]]]:
        """按情绪类目归并各标签目录 —— 「不需要太细分」。

        返回 {情绪类目: [(原始标签, 路径), ...]}。目录名正好是情绪名的，
        进对应类目；其余（default / collected / 自定义名）一律进「其他」。
        空类目不返回。顺序即 emotion.labels() 的顺序。
        """
        buckets: dict[str, list[tuple[str, Path]]] = {lab: [] for lab in emotion_labels()}
        for lab, paths in self._index.items():
            bucket = lab if lab in buckets else EMOTION_FALLBACK
            for p in paths:
                buckets[bucket].append((lab, p))
        return {lab: items for lab, items in buckets.items() if items}

    # ---------- 挑一张 ----------
    def pick(self, context_text: str = "", prefer_emotion: bool = True) -> Path | None:
        """按传入文本挑一张。文本为空则退到 default / 全部随机。

        prefer_emotion=True 时先按文本判出的「情绪」选目录（目录名 = 情绪名），
        这一步没命中再走原有的标签子串 → default → 全部随机。
        """
        if not self._index:
            return None
        text = str(context_text or "").lower()
        # ① AI 此刻的情绪（关键词规则，零 token）
        if prefer_emotion:
            emo = detect_emotion(text)
            if emo and emo in self._index:
                return random.choice(self._index[emo])
        # ② 标签名出现在文本里（default 不参与这一层）
        hit = [lab for lab in self._index if lab != DEFAULT_LABEL and lab.lower() in text]
        if hit:
            return random.choice(self._index[random.choice(hit)])
        # ③ default（散图）
        if DEFAULT_LABEL in self._index:
            return random.choice(self._index[DEFAULT_LABEL])
        # ④ 全部随机
        everything = [p for paths in self._index.values() for p in paths]
        return random.choice(everything) if everything else None


def read_base64(path: Path) -> str | None:
    """读成 base64 字符串，供跨容器发送（SnowLuma 与 AstrBot 不共享文件系统）。"""
    try:
        import base64

        return base64.b64encode(path.read_bytes()).decode()
    except OSError as e:
        logger.warning(f"[图恒宇] 读表情包失败：{e}")
        return None


def thumb_b64(path: Path, max_side: int = 320, quality: int = 80):
    """生成缩略图并返回 (base64, 宽, 高)；失败或没有 Pillow 时返回 None。

    用于插件页预览：原图动辄几百 KB～几 MB，直接内联会让响应过大；
    缩略到 max_side 后通常只剩几十 KB。
    """
    try:
        import base64
        import io

        from PIL import Image as _Image
    except Exception:
        return None
    try:
        with _Image.open(path) as im:
            im.seek(0)  # GIF 取第一帧
            # 统一转 RGB 存 JPEG（透明填白底）—— 远小于 PNG，适合预览
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                work = _Image.new("RGB", rgba.size, (255, 255, 255))
                work.paste(rgba, mask=rgba.split()[-1])
            else:
                work = im.convert("RGB")
            work.thumbnail((max_side, max_side))
            w, h = work.size
            buf = io.BytesIO()
            work.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode(), w, h
    except Exception as e:
        logger.warning(f"[图恒宇] 生成缩略图失败：{e}")
        return None


def save_collected(
    dest_root,
    src_path,
    label: str = "collected",
    max_bytes: int = 5 * 1024 * 1024,
) -> bool:
    """把一张收到的图存进表情包库（对话中自动收集）。

    去重：以内容 md5 命名，同内容第二次不再存。
    返回是否新存了一张。单张上限 max_bytes，超限丢弃。
    """
    src = Path(src_path)
    try:
        if not src.is_file():
            return False
        size = src.stat().st_size
        if size <= 0 or size > max_bytes:
            return False
        data = src.read_bytes()
    except OSError as e:
        logger.warning(f"[图恒宇] 收集表情包读取失败：{e}")
        return False

    digest = hashlib.md5(data).hexdigest()[:16]
    ext = src.suffix.lower()
    if ext not in IMAGE_EXTS:
        ext = ".png"
    dest_dir = Path(dest_root) / (str(label or "").strip() or "collected")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{digest}{ext}"
        if dest.exists():
            return False
        dest.write_bytes(data)
        return True
    except OSError as e:
        logger.warning(f"[图恒宇] 收集表情包写入失败：{e}")
        return False