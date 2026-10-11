"""Transport + state-dir helpers. STDLIB ONLY (imported by the fast client).

Transport: one JSON request line -> one JSON response line per connection.
  * POSIX: AF_UNIX socket inside a 0700 state dir (socket 0600) + SO_PEERCRED uid check.
  * --tcp (Windows-ready): 127.0.0.1:<ephemeral> + random token stored in the 0600 state file.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

STATE_NAME = "state.json"
SOCK_NAME = "rfh.sock"
MAX_UNIX_PATH = 100  # sun_path is 108 bytes on Linux, 104 on macOS


def state_dir(d: Optional[str] = None) -> Path:
    return Path(d or ".rf").absolute()


def ensure_private_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(d, 0o700)


def unix_sock_path(d: Path) -> Path:
    p = d / SOCK_NAME
    if len(str(p)) <= MAX_UNIX_PATH:
        return p
    # long project paths: fall back to a per-user runtime dir, keyed by state dir
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    h = hashlib.sha1(str(d).encode()).hexdigest()[:12]
    return base / f"rfh-{os.getuid()}-{h}.sock"


def read_state(d: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((d / STATE_NAME).read_text())
    except (OSError, ValueError):
        return None


def write_state(d: Path, data: Dict[str, Any]) -> None:
    tmp = d / (STATE_NAME + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, d / STATE_NAME)


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if sys.platform.startswith("linux"):  # zombie == dead for our purposes
        try:
            with open(f"/proc/{pid}/stat") as f:
                if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                    return False
        except OSError:
            return False
    return True


def connect(state: Dict[str, Any], timeout: float) -> socket.socket:
    if state.get("transport") == "tcp":
        s = socket.create_connection(("127.0.0.1", int(state["port"])), timeout=timeout)
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(state["sock"])
    return s


def request(state: Dict[str, Any], req: Dict[str, Any], timeout: float = 600.0) -> Dict[str, Any]:
    if state.get("token"):
        req = dict(req, token=state["token"])
    s = connect(state, timeout)
    try:
        s.sendall(json.dumps(req).encode() + b"\n")
        buf = bytearray()
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    if not buf:
        raise ConnectionError("daemon closed connection without reply")
    return json.loads(buf)


def wait_ready(d: Path, proc_pid: int, timeout: float) -> Optional[Dict[str, Any]]:
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        st = read_state(d)
        if st and st.get("ready") and st.get("pid"):
            try:
                if request(st, {"op": "ping"}, timeout=2).get("ok"):
                    return st
            except OSError:
                pass
        if not pid_alive(proc_pid):
            return None
        time.sleep(0.02)
    return None
