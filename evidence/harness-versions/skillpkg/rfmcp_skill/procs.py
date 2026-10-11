"""Process-tree helpers (stdlib only; Linux /proc, psutil if available elsewhere)."""
from __future__ import annotations

import os
import signal
import time
from typing import Dict, Iterable, List, Optional, Set

TOKEN_ENV = "RFMCP_SKILL_TOKEN"


def _proc_table() -> Dict[int, tuple]:
    """pid -> (ppid, pgid)"""
    out: Dict[int, tuple] = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return out
    for n in names:
        if not n.isdigit():
            continue
        try:
            with open(f"/proc/{n}/stat") as f:
                rest = f.read().rsplit(")", 1)[1].split()
            out[int(n)] = (int(rest[1]), int(rest[2]))
        except (OSError, IndexError, ValueError):
            continue
    return out


def descendants(root: int) -> List[int]:
    table = _proc_table()
    if not table:
        try:
            import psutil  # type: ignore

            return [c.pid for c in psutil.Process(root).children(recursive=True)]
        except Exception:
            return []
    kids: Dict[int, List[int]] = {}
    for pid, (ppid, _) in table.items():
        kids.setdefault(ppid, []).append(pid)
    res: List[int] = []
    stack = [root]
    while stack:
        p = stack.pop()
        for c in kids.get(p, []):
            res.append(c)
            stack.append(c)
    return res


def group_members(pgid: int) -> List[int]:
    return [pid for pid, (_, g) in _proc_table().items() if g == pgid]


def has_token(pid: int, token: str) -> bool:
    """True if the process environment carries our daemon token (guards against PID reuse)."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            return f"{TOKEN_ENV}={token}".encode() in f.read().split(b"\0")
    except OSError:
        return False


def alive(pids: Iterable[int]) -> List[int]:
    res = []
    for p in pids:
        try:
            os.kill(p, 0)
            with open(f"/proc/{p}/stat") as f:
                if f.read().rsplit(")", 1)[1].split()[0] != "Z":
                    res.append(p)
        except (OSError, IndexError):
            pass
    return res


def terminate(pids: List[int], grace: float = 2.0) -> List[int]:
    """SIGTERM, wait, SIGKILL. Returns pids that had to be SIGKILLed."""
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    t_end = time.monotonic() + grace
    while time.monotonic() < t_end and alive(pids):
        time.sleep(0.05)
    forced = alive(pids)
    for p in forced:
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    return forced


def token_procs(token: str, pgids: Optional[Set[int]] = None) -> List[int]:
    """All live processes carrying our token (optionally limited to given pgids)."""
    res = []
    for pid, (_, g) in _proc_table().items():
        if pgids is not None and g not in pgids:
            continue
        if has_token(pid, token):
            res.append(pid)
    return res
