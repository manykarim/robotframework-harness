"""Shared helpers for the desktop parity corpus.

Used by ``make_corpus.py`` (running under rf-mcp's Python, recording rf-mcp's
decisions) and by the harness tests (replaying them against
``rf_harness.runtime.desktop``). Stdlib only: imports neither rf-mcp nor the
harness, so both sides build identical fixtures.

* :class:`Placeholders` — machine-specific values (temp dirs, fake executables,
  a fake ``Xvfb`` process, PIDs) are written to the corpus as ``{TOKENS}``.
* :func:`build_focus_fakes` — a plain-Python PlatynUI runtime/window model built
  from a JSON spec; it records every call so both implementations must drive
  the runtime identically.
* :func:`normalize_text` / :func:`map_env_keys` — rf-mcp text/env names to
  harness names (``ROBOTMCP_`` -> ``RFH_``, "rf-mcp" -> "rf-harness").
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TEXT_RENAMES = (("ROBOTMCP_", "RFH_"), ("rf-mcp", "rf-harness"))

CORPUS_PATH = Path(__file__).resolve().parent / "corpus.json"


def load_corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


FAKE_EXECUTABLES = ("soffice", "mousepad", "someapp", "gnome-calculator", "xdotool")


def normalize_text(obj: Any) -> Any:
    """Apply the documented rf-mcp -> harness renames to every string (and key)."""
    if isinstance(obj, str):
        for old, new in TEXT_RENAMES:
            obj = obj.replace(old, new)
        return obj
    if isinstance(obj, list):
        return [normalize_text(v) for v in obj]
    if isinstance(obj, dict):
        return {normalize_text(k): normalize_text(v) for k, v in obj.items()}
    return obj


def map_env_keys(obj: Any) -> Any:
    """Rename ``ROBOTMCP_*`` dict keys to ``RFH_*`` (rf-mcp inputs -> harness inputs)."""
    if isinstance(obj, list):
        return [map_env_keys(v) for v in obj]
    if isinstance(obj, dict):
        return {
            (("RFH_" + k[len("ROBOTMCP_") :]) if isinstance(k, str) and k.startswith("ROBOTMCP_") else k): map_env_keys(
                v
            )
            for k, v in obj.items()
        }
    return obj


class Placeholders:
    """Creates the machine-specific fixtures and maps them to/from tokens."""

    PATH_TOKENS = ("{EXE_DIR}", "{RT_SOCKET}", "{RT_EMPTY}", "{SHOT_DIR}", "{ROOT}", "{TMP}")

    def __init__(self) -> None:
        tmp = tempfile.gettempdir()
        self.root = Path(tempfile.mkdtemp(prefix="rfh-desktop-corpus-"))
        exe_dir = self.root / "bin"
        exe_dir.mkdir()
        for name in FAKE_EXECUTABLES:
            exe = exe_dir / name
            exe.write_text("#!/bin/sh\nexit 0\n")
            exe.chmod(0o755)
        rt_socket = self.root / "rt-socket"
        rt_socket.mkdir()
        (rt_socket / "wayland-0").write_text("")
        rt_empty = self.root / "rt-empty"
        rt_empty.mkdir()
        shot_dir = self.root / "shots"
        shot_dir.mkdir()
        self._procs: list[subprocess.Popen] = []
        xvfb99 = self._fake_x_server(":99")
        xvfb98 = self._fake_x_server(":98")
        self.values = {
            "{EXE_DIR}": str(exe_dir),
            "{RT_SOCKET}": str(rt_socket),
            "{RT_EMPTY}": str(rt_empty),
            "{SHOT_DIR}": str(shot_dir),
            "{ROOT}": str(self.root),
            "{TMP}": tmp,
            "{SELF_PID}": str(os.getpid()),
            "{XVFB_99_PID}": str(xvfb99),
            "{XVFB_98_PID}": str(xvfb98),
        }

    def _fake_x_server(self, display: str) -> int:
        """A live process whose cmdline looks like ``.../Xvfb ... <display>``."""
        link = self.root / f"Xvfb{display.replace(':', '_')}" / "Xvfb"
        link.parent.mkdir()
        os.symlink(sys.executable, link)
        proc = subprocess.Popen(
            [str(link), "-c", "import time; time.sleep(900)", display],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._procs.append(proc)
        for _ in range(50):  # wait until /proc shows the final cmdline
            try:
                if Path(f"/proc/{proc.pid}/cmdline").read_bytes().endswith(display.encode() + b"\x00"):
                    break
            except OSError:
                pass
            time.sleep(0.02)
        return proc.pid

    def subst(self, obj: Any) -> Any:
        if isinstance(obj, str):
            for token, value in self.values.items():
                obj = obj.replace(token, value)
            return obj
        if isinstance(obj, list):
            return [self.subst(v) for v in obj]
        if isinstance(obj, dict):
            return {self.subst(k): self.subst(v) for k, v in obj.items()}
        return obj

    def unsubst(self, obj: Any) -> Any:
        if isinstance(obj, str):
            pairs = sorted(((t, self.values[t]) for t in self.PATH_TOKENS), key=lambda tv: len(tv[1]), reverse=True)
            for token, value in pairs:
                obj = obj.replace(value, token)
            return obj
        if isinstance(obj, (list, tuple)):
            return [self.unsubst(v) for v in obj]
        if isinstance(obj, dict):
            return {self.unsubst(k): self.unsubst(v) for k, v in obj.items()}
        return obj

    def close(self) -> None:
        for proc in self._procs:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(self.root, ignore_errors=True)


# --- fake PlatynUI runtime model ----------------------------------------------


class WindowSurfaceType:
    """Stand-in for ``platynui_native.WindowSurface`` (only used as a key)."""


class _Optional:
    """Hides the attributes listed in ``_absent`` (an optional runtime API)."""

    _absent: frozenset = frozenset()

    def __getattribute__(self, name: str) -> Any:
        if name in object.__getattribute__(self, "_absent"):
            raise AttributeError(name)
        return object.__getattribute__(self, name)


class FakeRect:
    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self._v = (x, y, w, h)

    def x(self) -> float:
        return self._v[0]

    def y(self) -> float:
        return self._v[1]

    def width(self) -> float:
        return self._v[2]

    def height(self) -> float:
        return self._v[3]

    def __repr__(self) -> str:
        return "Rect({},{},{},{})".format(*self._v)


def _act(behaviour: Any, calls: list, label: str) -> Any:
    calls.append(label)
    if behaviour == "raise":
        raise RuntimeError(f"{label} failed")
    return behaviour


class FakeSurface(_Optional):
    def __init__(self, spec: dict, calls: list) -> None:
        self._spec = spec
        self._calls = calls
        absent = set()
        if "activate" not in spec:
            absent.add("activate")
        if "accepts_user_input" not in spec:
            absent.add("accepts_user_input")
        self._absent = frozenset(absent)

    def activate(self) -> None:
        _act(self._spec.get("activate"), self._calls, "surface.activate")

    def accepts_user_input(self) -> Any:
        return _act(self._spec.get("accepts_user_input"), self._calls, "surface.accepts_user_input")


class FakeWindow(_Optional):
    def __init__(self, key: str, spec: dict, calls: list) -> None:
        self.key = key
        self.runtime_id = spec.get("runtime_id", key)
        self._spec = spec
        self._calls = calls
        attrs = dict(spec.get("attrs", {}))
        if "Bounds" in attrs and isinstance(attrs["Bounds"], list):
            attrs["Bounds"] = FakeRect(*attrs["Bounds"])
        self._attrs = attrs
        absent = set()
        patterns = spec.get("patterns", "absent")
        if patterns == "absent":
            absent.add("supported_patterns")
        if "surface" not in spec:
            absent.add("get_pattern")
        self._absent = frozenset(absent)

    def attribute(self, name: str) -> Any:
        if name not in self._attrs:
            raise KeyError(name)
        return self._attrs[name]

    def top_level_or_self(self) -> FakeWindow:
        return self

    def supported_patterns(self) -> Any:
        self._calls.append(f"{self.key}.supported_patterns")
        patterns = self._spec.get("patterns")
        if patterns == "raise":
            raise RuntimeError("supported_patterns failed")
        return patterns

    def get_pattern(self, pattern_type: Any) -> Any:
        self._calls.append(f"{self.key}.get_pattern")
        surface = self._spec.get("surface")
        if surface == "raise":
            raise RuntimeError("PatternNotSupported")
        if surface is None:
            return None
        return FakeSurface(surface, self._calls)


class FakeNode:
    def __init__(self, window: FakeWindow, runtime_id: str) -> None:
        self._window = window
        self.runtime_id = runtime_id
        self._attrs = {"Bounds": FakeRect(1, 2, 3, 4)}

    def attribute(self, name: str) -> Any:
        if name not in self._attrs:
            raise KeyError(name)
        return self._attrs[name]

    def top_level_or_self(self) -> FakeWindow:
        return self._window


class FakeRuntime(_Optional):
    """``evaluate`` is a list of per-call results (the last one repeats):
    ``"node:<window>"`` (an element inside that window), ``"none"``, ``"raise"``."""

    def __init__(self, spec: dict, windows: dict, calls: list) -> None:
        self._spec = spec
        self._windows = windows
        self._calls = calls
        self._evals = 0
        absent = {name for name in ("bring_to_front", "focus", "highlight", "clear_highlight") if name not in spec}
        if not spec.get("clear_cache", True):
            absent.add("clear_cache")
        self._absent = frozenset(absent)

    def clear_cache(self) -> None:
        self._calls.append("runtime.clear_cache")

    def evaluate_single(self, descriptor: str) -> Any:
        plan = self._spec.get("evaluate", ["node:main"])
        token = plan[min(self._evals, len(plan) - 1)]
        self._evals += 1
        self._calls.append(f"runtime.evaluate_single:{descriptor}")
        if token == "none":
            return None
        if token == "raise":
            raise RuntimeError("ElementNotFound")
        key = token.split(":", 1)[1]
        return FakeNode(self._windows[key], f"node-in-{key}")

    def desktop_info(self) -> Any:
        self._calls.append("runtime.desktop_info")
        return self._spec.get("desktop_info", {})

    def bring_to_front(self, node: Any, **kwargs: Any) -> None:
        behaviour = self._spec.get("bring_to_front")
        label = "runtime.bring_to_front" + "".join(f":{k}={v}" for k, v in sorted(kwargs.items()))
        if behaviour == "no_wait_ms" and "wait_ms" in kwargs:
            self._calls.append(label)
            raise TypeError("bring_to_front() got an unexpected keyword argument 'wait_ms'")
        _act("ok" if behaviour == "no_wait_ms" else behaviour, self._calls, label)

    def focus(self, node: Any) -> None:
        _act(self._spec.get("focus"), self._calls, "runtime.focus")

    def highlight(self, rect: Any, **kwargs: Any) -> None:
        behaviour = self._spec.get("highlight")
        label = f"runtime.highlight:{rect!r}" + "".join(f":{k}={v}" for k, v in sorted(kwargs.items()))
        if behaviour == "no_duration" and kwargs:
            self._calls.append(label)
            raise TypeError("highlight() got an unexpected keyword argument 'duration_ms'")
        _act("ok" if behaviour == "no_duration" else behaviour, self._calls, label)

    def clear_highlight(self) -> None:
        _act(self._spec.get("clear_highlight"), self._calls, "runtime.clear_highlight")


def build_focus_fakes(spec: dict) -> tuple[FakeRuntime, list]:
    """Build the fake runtime for one focus case; returns (runtime, call log)."""
    calls: list = []
    windows = {key: FakeWindow(key, wspec, calls) for key, wspec in spec.get("windows", {}).items()}
    if "main" not in windows:
        windows["main"] = FakeWindow("main", {}, calls)
    return FakeRuntime(spec.get("runtime", {}), windows, calls), calls
