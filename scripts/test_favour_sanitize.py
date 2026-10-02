"""sanitize_contexts / build_injection 的离线自测（不依赖 astrbot）。"""

import sys

sys.path.insert(0, "/sdcard/Download/tuhengyu-plan/plugin/astrbot_plugin_tuhengyu")

from core.favour import build_injection, sanitize_contexts  # noqa: E402


class FakePart:
    def __init__(self, text):
        self.text = text


def run():
    ctx = [
        {"role": "user", "content": "在吗"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "好呀\n%%FAV%% 2 | 热情直白 | 陌生人"},
                {"type": "think", "think": "I need to include the %%FAV%% line"},
            ],
        },
        {"role": "assistant", "content": "只有正文，无标记"},
        {"role": "assistant", "content": [FakePart("对象里的\n%%FAV%% 3 | x | y")]},
      "裸字符串消息 %%FAV%% 9 | z | w",
    ]
    n = sanitize_contexts(ctx)
    assert n == 4, f"改动处数应为 4，实际 {n}"
    assert ctx[1]["content"][0]["text"] == "好呀", ctx[1]["content"][0]["text"]
    assert "%%FAV%%" not in ctx[1]["content"][1]["think"]
    assert ctx[2]["content"] == "只有正文，无标记"
    assert "%%FAV%%" not in ctx[3]["content"][0].text
    assert "%%FAV%%" not in ctx[4]
    # 幂等：再跑一次应无改动
    assert sanitize_contexts(ctx) == 0, "重复清洗不应有改动"
    # 非 list 输入不炸
    assert sanitize_contexts(None) == 0
    assert sanitize_contexts({"a": 1}) == 0

    text = build_injection({"favour": 42, "attitude": "友善", "relationship": "熟人"})
    assert "42" in text and "唯一权威" in text, text[-120:]
    print("sanitize_contexts / build_injection OK")


run()