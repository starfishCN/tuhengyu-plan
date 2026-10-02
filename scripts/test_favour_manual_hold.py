"""手改保护 / 时间戳只在真变化时刷新的离线自测。"""

import sys
import tempfile
import time

sys.path.insert(0, "/sdcard/Download/tuhengyu-plan/plugin/astrbot_plugin_tuhengyu")

from core.favour import FavourStore  # noqa: E402


def run():
    d = tempfile.mkdtemp()
    s = FavourStore(d)

    s.set_state_by_key("1", favour=3, attitude="A", relationship="B")
    assert s.manual_hold("1", 24) == ["attitude", "relationship"], s.manual_hold("1", 24)
    assert s.manual_hold("1", 0) == [], "hours=0 应关闭保护"
    assert s.hold_until("1", 24), "应有到期时间"

    # 全部字段值都没变 → 不写盘、不动时间戳
    t1 = s.data["1"]["updated_at"]
    time.sleep(1.1)
    s.update("1", {"favour": 3, "attitude": "A", "relationship": "B"})
    assert s.data["1"]["updated_at"] == t1, "值没变不该刷时间戳"

    # 真变化才刷
    s.update("1", {"favour": 4})
    assert s.data["1"]["updated_at"] != t1, "值变了应刷时间戳"

    # 手改同一字段再次标记
    s.set_state_by_key("1", attitude="C")
    assert s.manual_hold("1", 24) == ["attitude", "relationship"]

    s.clear_manual_hold("1")
    assert s.manual_hold("1", 24) == [], "解除后不应再保护"
    assert s.hold_until("1", 24) == ""

    # 未手改过的条目不受保护
    s.update("2", {"favour": 1, "attitude": "X", "relationship": "Y"})
    assert s.manual_hold("2", 24) == []
    print("manual_hold / updated_at OK")


run()