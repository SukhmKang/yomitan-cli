from __future__ import annotations

import os
import subprocess
import sys
from typing import List


def read_clipboard() -> str:
    if sys.platform == "darwin":
        return read_clipboard_with_command(["pbpaste"])
    if os.name == "nt":
        return read_clipboard_with_command(
            ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"]
        )

    if command_exists("wl-paste"):
        return read_clipboard_with_command(["wl-paste", "--no-newline"])
    if command_exists("xclip"):
        return read_clipboard_with_command(["xclip", "-selection", "clipboard", "-out"])
    if command_exists("xsel"):
        return read_clipboard_with_command(["xsel", "--clipboard", "--output"])
    return ""


def read_clipboard_with_command(command: List[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1,
        )
    except subprocess.SubprocessError:
        return ""

    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


def command_exists(command: str) -> bool:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    return any(os.path.exists(os.path.join(path, command)) for path in paths)
