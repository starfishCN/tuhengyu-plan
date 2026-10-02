"""好感度：三维内心状态（好感 / 印象 / 关系）。

自研，不接第三方。三处取舍（针对第三方插件「状态块剥离不干净」的老 bug）：
    1. 模型只在回复末尾留**一行**状态行，格式 `%%FAV%% <好感> | <印象> | <关系>`；
    2. 解析时收全部匹配、整行全量剥离，缺字段保持原值；
       —— 块里没有方括号结构，碎块残留不可能发生。
    3. 好感度是**绝对值**（-100 ~ 100），不是增量；当前值每轮注入给模型。

存盘（均在插件数据目录）：
    favour.json         当前三维状态（含昵称 / 更新时间）
    favour_history.json 好感度历史采样（画曲线用）
    favour_curve.json   由人设生成的「变化曲线」参数

键 = 用户 QQ；开启会话独立时 = "<会话标识>_<用户 QQ>"。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time

logger = logging.getLogger("astrbot")

MARKER = "%%FAV%%"

DEFAULT_STATE: dict = {"favour": 0, "attitude": "中立", "relationship": "陌生人"}

# 找出行内的状态行（同一回复里允许出现多行，全部收走）
_MARKER_FIND = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"([^\n]*)", re.M)
# 剥离：连行尾换行一起吃掉，避免留下空行
_MARKER_STRIP = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[^\n]*\n?", re.M)

BANDS = (
    (75, "亲密信赖", "热情、主动、亲近，可以用亲昵的称呼"),
    (40, "友好", "积极、乐于搭话、带点好情绪"),
    (-10, "中立礼貌", "客气、保持距离、话说得标准"),
    (-50, "反感", "冷淡、简短、不耐烦，能敷衍就敷衍"),
    (-999, "厌恶敌对", "极短、带刺，不想搭理"),
)

# 默认「变化曲线」＝原有写死规则，作为 LLM 生成失败 / 未启用时的兜底。
DEFAULT_CURVE: dict = {
    "version": 1,
    "source": "default",
    "persona_fingerprint": "",
    "generated_at": "",
    "bands": [
        {"min": 75, "name": "亲密信赖", "desc": "热情、主动、亲近，可以用亲昵的称呼"},
        {"min": 40, "name": "友好", "desc": "积极、乐于搭话、带点好情绪"},
        {"min": -10, "name": "中立礼貌", "desc": "客气、保持距离、话说得标准"},
        {"min": -50, "name": "反感", "desc": "冷淡、简短、不耐烦，能敷衍就敷衍"},
        {"min": -999, "name": "厌恶敌对", "desc": "极短、带刺，不想搭理"},
    ],
    "deltas": {
        "positive": [1, 3],
        "affection": [2, 5],
        "negative": [-10, -3],
        "insult": [-8, -4],
    },
    "notes": "",
}


def band(favour: int) -> tuple[str, str]:
    """好感度 → (区间名, 语气要求)。默认曲线。"""
    for threshold, name, desc in BANDS:
        if favour >= threshold:
            return name, desc
    return BANDS[-1][1], BANDS[-1][2]


def _curve_bands(curve) -> list[tuple[int, str, str]]:
    """从曲线里取 bands；非法则回落默认。返回按阈值降序。"""
    if isinstance(curve, dict) and isinstance(curve.get("bands"), list) and curve["bands"]:
        out = []
        for b in curve["bands"]:
            if not isinstance(b, dict):
                continue
            try:
                out.append((int(b["min"]), str(b["name"]), str(b.get("desc", ""))))
            except Exception:
                continue
        if out:
            out.sort(key=lambda x: x[0], reverse=True)
            return out
    return [(b["min"], b["name"], b["desc"]) for b in DEFAULT_CURVE["bands"]]


def band_of(favour: int, curve=None) -> tuple[str, str]:
    """按给定曲线取区间名与语气。"""
    bands = _curve_bands(curve)
    for threshold, name, desc in bands:
        if favour >= threshold:
            return name, desc
    return bands[-1][1], bands[-1][2]


def normalize_curve(raw) -> dict:
    """把模型 / 用户给的曲线补全、夹到合法范围。非法项回落默认。"""
    curve = json.loads(json.dumps(DEFAULT_CURVE))  # 深拷贝
    if not isinstance(raw, dict):
        return curve

    bands = raw.get("bands")
    if isinstance(bands, list) and bands:
        clean = []
        for b in bands:
            if not isinstance(b, dict):
                continue
            try:
                mn = int(b.get("min"))
            except Exception:
                continue
            name = str(b.get("name", "")).strip()
            if not name:
                continue
            clean.append(
                {
                    "min": max(-1000, min(100, mn)),
                    "name": name[:20],
                    "desc": str(b.get("desc", "")).strip()[:60],
                }
            )
        if clean:
            clean.sort(key=lambda x: x["min"], reverse=True)
            curve["bands"] = clean

    deltas = raw.get("deltas")
    if isinstance(deltas, dict):
        clean_d = {}
        for k in ("positive", "affection", "negative", "insult"):
            v = deltas.get(k)
            if isinstance(v, (list, tuple)) and len(v) == 2:
                try:
                    a, b = int(v[0]), int(v[1])
                except Exception:
                    continue
                lo, hi = min(a, b), max(a, b)
                clean_d[k] = [max(-100, lo), min(100, hi)]
        if clean_d:
            curve["deltas"] = {**curve["deltas"], **clean_d}

    curve["notes"] = str(raw.get("notes", "")).strip()[:200]
    if raw.get("source"):
        curve["source"] = str(raw["source"])[:20]
    if raw.get("persona_fingerprint"):
        curve["persona_fingerprint"] = str(raw["persona_fingerprint"])
    if raw.get("generated_at"):
        curve["generated_at"] = str(raw["generated_at"])
    return curve


def persona_fingerprint(text: str) -> str:
    """人设正文的指纹：人设没变就不重算曲线。"""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def parse_curve_json(text: str):
    """从模型输出里抠出曲线 JSON。失败返回 None。"""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):  # 去掉可能的 markdown 代码块围栏
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        obj = json.loads(s[i : j + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def parse_state_marker(text: str) -> tuple[str, dict | None]:
    """从回复里收走所有状态行。

    返回 (给用户看的正文, 状态更新 dict 或 None)。更新只覆盖解析到的字段。
    """
    if not text or MARKER not in text:
        return text, None
    update: dict = {}
    for m in _MARKER_FIND.finditer(text):
        parts = [p.strip() for p in m.group(1).split("|")]
        if not parts:
            continue
        raw = parts[0].strip().lstrip("+")
        if raw:
            try:
                update["favour"] = int(raw)
            except ValueError:
                pass
        if len(parts) > 1 and parts[1]:
            update["attitude"] = parts[1]
        if len(parts) > 2 and parts[2]:
            update["relationship"] = parts[2]
    cleaned = _MARKER_STRIP.sub("", text).strip()
    return cleaned, (update or None)


def strip_marker_lines(text: str) -> str:
    """把文本里所有状态行整行去掉（用于清洗历史上下文，不动正文其他行）。"""
    if not text or MARKER not in text:
        return text
    kept = [ln for ln in text.split("\n") if MARKER not in ln]
    return "\n".join(kept).strip()


def sanitize_contexts(contexts) -> int:
    """就地把历史上下文里残留的状态行清掉，返回改动处数。

    历史里留着上一轮的 `%%FAV%% 12 | …`，模型会照着抄，导致手动改过的数值
    聊几轮又被拉回旧值。清掉之后模型只能看 system prompt 里的权威值。
    只删行，不删消息；不碰 system_prompt（那里的指令行本身就含标记）。
    """
    if not isinstance(contexts, list):
        return 0
    changed = 0

    def clean(value):
        if isinstance(value, str) and MARKER in value:
            new = strip_marker_lines(value)
            if new != value:
                return new, True
        return value, False

    for msg in contexts:
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                new, hit = clean(content)
                if hit:
                    msg["content"] = new
                    changed += 1
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        for field_name in ("text", "think", "content"):
                            if field_name in part:
                                new, hit = clean(part[field_name])
                                if hit:
                                    part[field_name] = new
                                    changed += 1
                    elif isinstance(part, str):
                        new, hit = clean(part)
                        if hit:
                            content[content.index(part)] = new
                            changed += 1
                    else:
                        # ContentPart 之类的对象
                        for field_name in ("text", "think"):
                            if hasattr(part, field_name):
                                cur = getattr(part, field_name)
                                new, hit = clean(cur)
                                if hit:
                                    try:
                                        setattr(part, field_name, new)
                                        changed += 1
                                    except Exception:
                                        pass
        elif isinstance(msg, str):
            new, hit = clean(msg)
            if hit:
                contexts[contexts.index(msg)] = new
                changed += 1
    return changed


def build_injection(state: dict, curve=None) -> str:
    """拼出注入 system_prompt 的状态说明 + 更新指令。curve 给定时用其区间与幅度。"""
    favour = int(state.get("favour", 0) or 0)
    name, desc = band_of(favour, curve)

    d = None
    if isinstance(curve, dict) and isinstance(curve.get("deltas"), dict):
        d = curve["deltas"]
    if not isinstance(d, dict):
        d = DEFAULT_CURVE["deltas"]

    def rng(key):
        v = d.get(key, DEFAULT_CURVE["deltas"][key])
        try:
            return f"{int(v[0])}~{int(v[1])}"
        except Exception:
            v = DEFAULT_CURVE["deltas"][key]
            return f"{v[0]}~{v[1]}"

    # 低档位给「时机许可」：插件只负责什么时候可以冷、可以怼，
    # 具体说什么一律由人设决定（人格卡里已有自己的怼人口径）。
    if favour < -50:
        tip = (
            "到这个份上，你可以直接怼回去、也可以干脆不搭理：短句，带刺不带脏字，"
            "一两句收场，不追着吵。说什么，按你自己的人设来。\n"
        )
    elif favour < -10:
        tip = (
            "你对这人已经不太耐烦，可以冷淡、可以怼回去：短句，带笑不带脏字，"
            "一两句收场，不追着吵。说什么，按你自己的人设来。\n"
        )
    else:
        tip = ""
    return (
        "\n\n[内心状态 · 机密]\n"
        f"你对该用户当前的关系是：{state.get('relationship', '陌生人')}；"
        f"好感度：{favour}（-100 极度厌恶 ~ 100 挚爱）；"
        f"你对他的印象是：{state.get('attitude', '中立')}。\n"
        f"此刻你处于「{name}」区间，说话方式应是：{desc}。\n"
        f"{tip}"
        "每一轮回复都必须在最后另起一行，写出更新后的状态（这一行会由系统自动收走，用户看不到）：\n"
        f"{MARKER} <好感度整数> | <印象> | <关系>\n"
        "规则：好感度写绝对值、不是增减量；"
        f"普通正面互动 {rng('positive')}，亲密 / 示好互动 {rng('affection')}，"
        f"普通负面互动 {rng('negative')}，冒犯 / 辱骂 {rng('insult')}；"
        "提升要谨慎、下降要干脆；印象和关系各一句话，且必须与好感度一致；"
        "即使本轮没有任何变化，也要照写当前值，不得省略这一行；"
        "不要用任何其他形式复述、暗示或解释这一行。\n"
        "注意：本段数值是唯一权威的当前状态。上面历史消息里若出现过状态行，"
        "那是过期记录，一律作废，不得沿用其中的数字。"
    )


class FavourStore:
    """三维状态的读写。单文件 JSON，改动即落盘。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "favour.json")
        self.data: dict = self._load()

    # ---------- 存取 ----------
    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(f"[图恒宇] 读取好感度数据失败：{e}")
            return {}

    def _save(self) -> None:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"[图恒宇] 写入好感度数据失败：{e}")

    # ---------- 键 ----------
    @staticmethod
    def key(user_id: str, session_id: str | None = None) -> str:
        uid = str(user_id or "").strip()
        sid = str(session_id or "").strip()
        return f"{sid}_{uid}" if sid and uid else uid

    # ---------- 读写状态 ----------
    def get(self, user_id: str, session_id: str | None = None) -> dict:
        k = self.key(user_id, session_id)
        state = self.data.get(k)
        if not isinstance(state, dict):
            return dict(DEFAULT_STATE)
        out = dict(DEFAULT_STATE)
        out.update({kk: vv for kk, vv in state.items() if vv not in (None, "")})
        return out

    def update(
        self,
        user_id: str,
        patch: dict,
        session_id: str | None = None,
        name: str = "",
    ) -> dict:
        """把 patch 合并进当前状态后落盘。favour 会被夹到 -100~100。"""
        k = self.key(user_id, session_id)
        if not k:
            return dict(DEFAULT_STATE)
        state = self.get(user_id, session_id)
        for field in ("favour", "attitude", "relationship"):
            if field not in patch:
                continue
            val = patch[field]
            if field == "favour":
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    continue
                val = max(-100, min(100, val))
            else:
                val = str(val).strip()
                if not val:
                    continue
            state[field] = val
        if name:
            state["name"] = str(name).strip()[:40]
        state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.data[k] = state
        self._save()
        return state

    def set_state(
        self,
        user_id: str,
        favour=None,
        attitude=None,
        relationship=None,
        name=None,
        session_id: str | None = None,
    ) -> dict | None:
        """手动覆写某个用户的各项；None 表示该字段不动。"""
        k = self.key(user_id, session_id)
        if not k:
            return None
        state = self.get(user_id, session_id)
        if favour is not None:
            try:
                state["favour"] = max(-100, min(100, int(favour)))
            except (TypeError, ValueError):
                pass
        if attitude is not None and str(attitude).strip():
            state["attitude"] = str(attitude).strip()
        if relationship is not None and str(relationship).strip():
            state["relationship"] = str(relationship).strip()
        if name is not None and str(name).strip():
            state["name"] = str(name).strip()[:40]
        state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.data[k] = state
        self._save()
        return state

    def list_all(self) -> list[dict]:
        """列出所有条目（供页签展示）。按好感降序。"""
        out = []
        for k, v in self.data.items():
            if not isinstance(v, dict):
                continue
            st = dict(DEFAULT_STATE)
            st.update({kk: vv for kk, vv in v.items() if vv not in (None, "")})
            try:
                fv = int(st.get("favour", 0) or 0)
            except (TypeError, ValueError):
                fv = 0
            out.append(
                {
                    "key": k,
                    "favour": fv,
                    "attitude": str(st.get("attitude", "中立")),
                    "relationship": str(st.get("relationship", "陌生人")),
                    "name": str(st.get("name", "")),
                    "updated_at": str(st.get("updated_at", "")),
                }
            )
        out.sort(key=lambda x: x["favour"], reverse=True)
        return out

    def remove(self, user_id: str, session_id: str | None = None) -> None:
        k = self.key(user_id, session_id)
        if k in self.data:
            self.data.pop(k, None)
            self._save()

    def reset(self, user_id: str, session_id: str | None = None) -> None:
        k = self.key(user_id, session_id)
        if k in self.data:
            self.data[k] = dict(DEFAULT_STATE)
            self._save()

    # ---------- 按完整键操作（页签用：键可能形如 "<会话>_<QQ>"） ----------
    def set_state_by_key(
        self, key: str, favour=None, attitude=None, relationship=None, name=None
    ) -> dict | None:
        k = str(key or "").strip()
        if not k:
            return None
        state = self.get(k)
        if favour is not None:
            try:
                state["favour"] = max(-100, min(100, int(favour)))
            except (TypeError, ValueError):
                pass
        if attitude is not None and str(attitude).strip():
            state["attitude"] = str(attitude).strip()
        if relationship is not None and str(relationship).strip():
            state["relationship"] = str(relationship).strip()
        if name is not None and str(name).strip():
            state["name"] = str(name).strip()[:40]
        state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.data[k] = state
        self._save()
        return state

    def remove_by_key(self, key: str) -> None:
        k = str(key or "").strip()
        if k in self.data:
            self.data.pop(k, None)
            self._save()

    def reset_by_key(self, key: str) -> None:
        k = str(key or "").strip()
        if k:
            self.data[k] = dict(DEFAULT_STATE)
            self._save()


class HistoryStore:
    """好感度历史采样（画曲线用）。值没变就不重复记。"""

    def __init__(self, data_dir: str, cap: int = 300):
        self.path = os.path.join(data_dir, "favour_history.json")
        self.cap = cap
        self.data: dict = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(f"[图恒宇] 读取好感度历史失败：{e}")
            return {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"[图恒宇] 写入好感度历史失败：{e}")

    def record(
        self, uid: str, favour: int, attitude: str = "", relationship: str = ""
    ) -> None:
        k = str(uid or "")
        if not k:
            return
        arr = self.data.get(k)
        if not isinstance(arr, list):
            arr = []
        try:
            fv = int(favour)
        except (TypeError, ValueError):
            return
        if arr and arr[-1].get("favour") == fv:
            return  # 值没变不重复记，曲线靠变化点成型
        arr.append(
            {
                "t": time.strftime("%Y-%m-%d %H:%M:%S"),
                "favour": fv,
                "attitude": str(attitude or ""),
                "relationship": str(relationship or ""),
            }
        )
        if len(arr) > self.cap:
            arr = arr[-self.cap :]
        self.data[k] = arr
        self._save()

    def get(self, uid: str, limit: int = 120) -> list:
        arr = self.data.get(str(uid or ""))
        if not isinstance(arr, list):
            return []
        return arr[-limit:]

    def remove(self, uid: str) -> None:
        if str(uid or "") in self.data:
            self.data.pop(str(uid), None)
            self._save()


class CurveStore:
    """好感度变化曲线参数（favour_curve.json）。

    由人设驱动、LLM 生成，落盘复用；人设指纹没变就不重算。
    读取失败 / 未生成时回落 DEFAULT_CURVE。
    """

    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "favour_curve.json")
        self.curve: dict = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            return normalize_curve(raw)
        except FileNotFoundError:
            return json.loads(json.dumps(DEFAULT_CURVE))
        except Exception as e:
            logger.warning(f"[图恒宇] 读取好感度曲线失败：{e}")
            return json.loads(json.dumps(DEFAULT_CURVE))

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.curve, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.warning(f"[图恒宇] 写入好感度曲线失败：{e}")

    def get(self) -> dict:
        return self.curve if isinstance(self.curve, dict) else dict(DEFAULT_CURVE)

    def set(self, raw, fingerprint: str = "", source: str = "llm") -> dict:
        """写入一条（模型 / 手改）曲线，补全夹逼后落盘。返回生效的曲线。"""
        curve = normalize_curve(raw)
        curve["source"] = str(source)[:20]
        if fingerprint:
            curve["persona_fingerprint"] = str(fingerprint)
        curve["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.curve = curve
        self._save()
        return curve

    def reset(self) -> dict:
        """清掉曲线，回到内置默认参数。"""
        self.curve = json.loads(json.dumps(DEFAULT_CURVE))
        self.curve["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save()
        return self.curve