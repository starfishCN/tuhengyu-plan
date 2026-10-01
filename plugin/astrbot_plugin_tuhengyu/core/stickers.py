"""表情包：按标签挑一张图 —— 不接 embedding，不接向量库。

约定（目录即标签）：
    data/stickers/<标签>/xxx.png      → 标签 = 子目录名
    data/stickers/xxx.png             → 标签 = default（散图）

分类维度 = 意图（core/intent.py 的 8 类：拒绝/道歉/攻击/亲昵/赞同/提问/认输/害羞）。

选图优先级（prefer_intent=True 时）：
    ① 先按「AI 此刻的意图」定位目录 —— 关键词规则，从传入文本里判出
       意图类目，目录同名就随机取一张
    ② 否则标签名出现在文本里 → 该标签随机一张
    ③ 再否则用 default 标签（散图）
    ④ 再否则从全部里随机
    ⑤ 一张图都没有 → None

给图片归类（把 default / collected 里的图打上意图标签）走大模型识图，
见 core/classify.py；那一步要调一次模型，只在点「自动归类」时发生。
选图本身仍是零 token。
"""
from __future__ import annotations

import hashlib
import logging
import random
import shutil
from pathlib import Path

from .intent import FALLBACK as INTENT_FALLBACK
from .intent import detect as detect_intent
from .intent import labels as intent_labels

logger = logging.getLogger("astrbot")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
DEFAULT_LABEL = "default"
# 上传单张上限（WebUI 上传用；对话收集另有 5MB 上限）
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# 归入「其他」的系统目录（不是用户分类）
SYSTEM_LABELS = {DEFAULT_LABEL, "collected"}


class StickerLibrary:
    """本地表情包库。只做「扫目录 + 挑一张」。"""

    def __init__(self, roots):
        if isinstance(roots, (str, Path)):
            roots = [roots]
        self.roots = [Path(r) for r in roots]
        self._index: dict[str, list[Path]] = {}
        # 写入目标：第一个根 = 数据目录（用户放图 / 上传落点）
        self.primary_root = self.roots[0] if self.roots else None
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

    def groups_by_intent(self) -> dict[str, list[tuple[str, Path]]]:
        """展示用分组：按意图 / 分类归组。

        规则：
          - 目录名是内置意图名（拒绝 / 道歉 / …）→ 该类目
          - default / collected → 「其他」
          - 其余目录名（用户在 WebUI 里自建的分类）→ 各自独立一类
        顺序：内置意图 →（用户分类，按名）→「其他」。空类目不返回。
        """
        order_int = [lab for lab in intent_labels() if lab != INTENT_FALLBACK]
        out: dict[str, list[tuple[str, Path]]] = {}
        for lab in order_int:
            items = [(lab, p) for p in self._index.get(lab, [])]
            if items:
                out[lab] = items
        extras: dict[str, list[tuple[str, Path]]] = {}
        others: list[tuple[str, Path]] = []
        for lab, paths in self._index.items():
            if lab in order_int:
                continue
            if lab in SYSTEM_LABELS:
                others.extend((lab, p) for p in paths)
            else:
                extras[lab] = [(lab, p) for p in paths]
        for lab in sorted(extras):
            out[lab] = extras[lab]
        if others:
            out[INTENT_FALLBACK] = others
        return out

    def classify_targets(self) -> list[tuple[str, Path]]:
        """可被「自动归类」处理的图：位于 default / collected 的散图。

        返回 (当前标签, 路径)。已归到意图类目或用户自建分类的图不重复处理。
        """
        out: list[tuple[str, Path]] = []
        for lab in SYSTEM_LABELS:
            for p in self._index.get(lab, []):
                out.append((lab, p))
        return out

    # ---------- 写入（WebUI：新建分类 / 上传表情包） ----------
    @staticmethod
    def _bad_name(name: str) -> str | None:
        """校验分类名，返回错误说明或 None。"""
        if not name:
            return "分类名不能为空"
        if len(name) > 20:
            return "分类名太长（≤20 字）"
        if "/" in name or "\\" in name or name.startswith("."):
            return "分类名不能含 / \\ 或以 . 开头"
        return None

    def categories(self) -> list[str]:
        """所有真实目录名（上传目标下拉用）。"""
        return sorted(self._index)

    def add_category(self, name: str) -> tuple[bool, str]:
        """在数据目录下新建一个分类（子目录）。返回 (是否成功, 说明)。"""
        name = str(name or "").strip()
        err = self._bad_name(name)
        if err:
            return False, err
        if self.primary_root is None:
            return False, "没有可写的数据目录"
        target = self.primary_root / name
        try:
            if target.exists():
                return False, f"分类「{name}」已存在"
            target.mkdir(parents=True, exist_ok=False)
        except OSError as e:
            return False, f"建目录失败：{e}"
        self.reload()
        return True, f"已新建分类「{name}」"

    def save_image(self, category: str, filename: str, data: bytes) -> tuple[bool, str]:
        """把一张图存进某个分类（按内容 md5 命名去重）。返回 (是否成功, 说明)。"""
        category = str(category or "").strip()
        err = self._bad_name(category)
        if err:
            return False, err
        if not data:
            return False, "空文件"
        if len(data) > MAX_UPLOAD_BYTES:
            return False, f"文件超过上限（{MAX_UPLOAD_BYTES // 1024 // 1024}MB）"
        ext = Path(str(filename or "")).suffix.lower()
        if ext not in IMAGE_EXTS:
            return False, "只支持图片（png / jpg / jpeg / gif / webp / bmp）"
        if self.primary_root is None:
            return False, "没有可写的数据目录"
        dest_dir = self.primary_root / category
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.md5(data).hexdigest()[:16]
            dest = dest_dir / f"{digest}{ext}"
            if dest.exists():
                return False, "这张图库里已有（按内容去重）"
            dest.write_bytes(data)
        except OSError as e:
            return False, f"写入失败：{e}"
        self.reload()
        return True, "已添加"

    def move_image(self, path: Path, category: str) -> tuple[bool, str]:
        """把一张已存在的图移动到一个分类目录下（识图归类用）。返回 (是否成功, 说明)。"""
        category = str(category or "").strip()
        err = self._bad_name(category)
        if err:
            return False, err
        src = Path(path)
        if not src.is_file():
            return False, "源文件不存在"
        if self.primary_root is None:
            return False, "没有可写的数据目录"
        dest_dir = self.primary_root / category
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest.exists():
                return False, "目标已存在同名文件"
            shutil.move(str(src), str(dest))
        except OSError as e:
            return False, f"移动失败：{e}"
        self.reload()
        return True, f"已归入「{category}」"

    # ---------- 挑一张 ----------
    def pick(self, context_text: str = "", prefer_intent: bool = True) -> Path | None:
        """按传入文本挑一张。文本为空则退到 default / 全部随机。

        prefer_intent=True 时先按文本判出的「意图」选目录（目录名 = 意图名），
        这一步没命中再走原有的标签子串 → default → 全部随机。
        """
        if not self._index:
            return None
        text = str(context_text or "").lower()
        # ① AI 此刻的意图（关键词规则，零 token）
        if prefer_intent:
            intent = detect_intent(text)
            if intent and intent in self._index:
                return random.choice(self._index[intent])
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