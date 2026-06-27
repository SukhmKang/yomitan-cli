from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty


def hide_cursor() -> None:
    print("\033[?25l", end="")


def show_cursor() -> None:
    print("\033[?25h", end="")


def enable_single_keypress_input() -> Optional[Any]:
    if not sys.stdin.isatty():
        return None
    if os.name == "nt":
        return None

    settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin)
    return settings


def restore_terminal(settings: Optional[Any]) -> None:
    if settings is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)


def read_keypress() -> Optional[str]:
    if not sys.stdin.isatty():
        return None

    data = read_key_bytes()
    if not data:
        return None
    if data.lower() == b"q":
        return "quit"
    if data == b"\t":
        return "toggle"
    if data in {b"\x1b[D", b"\x1bOD"}:
        return "left"
    if data in {b"\x1b[C", b"\x1bOC"}:
        return "right"
    return None


def read_key_bytes() -> bytes:
    if not sys.stdin.isatty():
        return b""
    if os.name == "nt":
        return read_windows_key_bytes()

    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
        return b""

    data = os.read(sys.stdin.fileno(), 32)
    if data != b"\x1b":
        return data

    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        timeout = max(0, deadline - time.monotonic())
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if not readable:
            break
        data += os.read(sys.stdin.fileno(), 32)
        if data in {b"\x1b[C", b"\x1b[D", b"\x1bOC", b"\x1bOD"}:
            break
    return data


def read_windows_key_bytes() -> bytes:
    if not msvcrt.kbhit():
        return b""

    data = msvcrt.getwch()
    if data in {"\x00", "\xe0"} and msvcrt.kbhit():
        code = msvcrt.getwch()
        if code == "K":
            return b"\x1b[D"
        if code == "M":
            return b"\x1b[C"
        return code.encode(errors="ignore")
    return data.encode(errors="ignore")
