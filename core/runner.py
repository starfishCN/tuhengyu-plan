"""执行 shell 命令，并把输出逐行推出去（给面板实时日志用）。"""
import asyncio
import os
from typing import Callable

# 关键修复（2026-10-01，实测踩坑）：
#   1. 子进程必须 DEVNULL stdin —— 否则 apt/debconf 想读输入时会永久挂起；
#   2. DEBIAN_FRONTEND=noninteractive —— 无终端环境下禁止 debconf 弹对话框；
#   3. TERM=dumb —— 避免 ncurses 探测并把控制字符灌进日志。
CHILD_ENV = {
    **os.environ,
    "DEBIAN_FRONTEND": "noninteractive",
    "TERM": "dumb",
}


async def run_stream(cmd: str, on_line: Callable[[str], None]) -> int:
    """跑一条 shell 命令，stdout/stderr 合并，逐行回调。返回退出码。"""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=CHILD_ENV,
    )
    assert proc.stdout is not None
    async for raw in proc.stdout:
        on_line(raw.decode(errors="replace").rstrip())
    return await proc.wait()


async def run_stream_all(cmds, on_line, on_step=None) -> int:
    """顺序跑多条命令，任一条非 0 就停。返回最后一条的退出码。"""
    code = 0
    for i, cmd in enumerate(cmds):
        if on_step:
            on_step(i, cmd)
        on_line(f"$ {cmd}")
        code = await run_stream(cmd, on_line)
        on_line(f"[退出码] {code}")
        if code != 0:
            on_line("!! 该步骤失败，已停止。")
            break
    return code
