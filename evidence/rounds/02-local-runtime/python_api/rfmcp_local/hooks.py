"""Per-step hooks run INSIDE the helper (same process + RF context as the keyword).

pre(step)  -> None to proceed, or a dict to refuse the step (it is then not executed)
post(step, rec) -> may enrich/redact the compact record

`step` is a StepCtx: name, args (list[str], may be rewritten), assign, owner (resolved
through the live RF namespace, i.e. rf-mcp's S5 pattern), kw (running model node).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from robot.libraries.BuiltIn import BuiltIn
from robot.running.context import EXECUTION_CONTEXTS


@dataclass
class StepCtx:
    kw: Any
    name: str
    args: List[str]
    assign: List[str]
    owner: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def resolve_owner(name: str) -> Optional[str]:
    """Authoritative keyword -> library/resource resolution via the live namespace."""
    ctx = EXECUTION_CONTEXTS.current
    if ctx is None or not name:
        return None
    try:
        runner = ctx.namespace.get_runner(name, recommend_on_failure=False)
    except TypeError:  # RF < 7 signature
        runner = ctx.namespace.get_runner(name)
    except Exception:
        return None
    kw = getattr(runner, "keyword", None)
    owner = getattr(kw, "owner", None)
    return getattr(owner, "name", None) or getattr(kw, "libname", None)


class Hook:
    name = "hook"

    def pre(self, step: StepCtx) -> Optional[Dict[str, Any]]:
        return None

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        return None


# ---------------------------------------------------------------- redaction
SECRET_KEY = re.compile(r"(pass(word|wd)?|secret|token|auth(orization)?|api[_-]?key|cookie|bearer)", re.I)


class Redactor(Hook):
    """Learns secret values from named args (password=..., auth=..., headers with Authorization)
    and scrubs them from everything that leaves the helper (args, messages, logs, return values)."""

    name = "redact"

    def __init__(self) -> None:
        self.secrets: Set[str] = set()

    def _collect(self, value: Any) -> None:
        if isinstance(value, str):
            if len(value) >= 4:
                self.secrets.add(value)
        elif isinstance(value, dict):
            for v in value.values():  # dict passed to a secret-named arg: all values are secret
                self._collect(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self._collect(v)

    def pre(self, step: StepCtx) -> None:
        for a in step.args:
            m = re.match(r"^([\w-]+)=(.+)$", a, re.S)
            if not m or not SECRET_KEY.search(m.group(1)):
                continue
            raw = m.group(2)
            try:
                val = BuiltIn().replace_variables(raw)
            except Exception:
                val = raw
            self._collect(val)
        return None

    def scrub(self, s: Any) -> Any:
        if not isinstance(s, str) or not self.secrets:
            return s
        for sec in sorted(self.secrets, key=len, reverse=True):
            s = s.replace(sec, "***")
        return s

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        for a in step.assign:  # ${token}=  Set Variable ...  -> learn the assigned value
            var = a.rstrip("= ").strip()
            if SECRET_KEY.search(var):
                try:
                    self._collect(BuiltIn().get_variable_value(var))
                except Exception:
                    pass
        rec["args"] = [self.scrub(a) for a in rec.get("args", [])]
        for k in ("msg", "ret"):
            if k in rec:
                rec[k] = self.scrub(rec[k])
        if "logs" in rec:
            rec["logs"] = [self.scrub(x) for x in rec["logs"]]


# ---------------------------------------------------------------- hints
class Hints(Hook):
    """rf-mcp's pure hint engine (robotmcp.utils.hints) on failures, if importable."""

    name = "hints"

    def __init__(self, max_hints: int = 2) -> None:
        self.max_hints = max_hints
        try:
            from robotmcp.utils.hints import HintContext, generate_hints  # type: ignore

            self._gen, self._ctx = generate_hints, HintContext
        except Exception as e:  # pragma: no cover
            self._gen = None
            self.error = repr(e)

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        if self._gen is None or rec.get("status") != "FAIL":
            return
        try:
            order = [o for o in (step.owner, "BuiltIn") if o]  # authoritative owner -> library-aware hints
            hs = self._gen(self._ctx(session_id="local", keyword=step.name, arguments=list(step.args),
                                     error_text=rec.get("msg") or "", session_search_order=order))
        except Exception as e:
            rec["hints_error"] = repr(e)
            return
        out = []
        for h in hs[: self.max_hints]:
            ex = h.get("examples") or []
            out.append({"title": h.get("title"), "message": (h.get("message") or "")[:300],
                        "example": ex[0] if ex else None})
        if out:
            rec["hints"] = out


# ---------------------------------------------------------------- Browser fast-fail
_BROWSER_LOCATOR_KWS = {
    "click", "fill text", "type text", "fill secret", "type secret", "check checkbox", "uncheck checkbox",
    "hover", "get text", "select options by", "press keys", "focus", "clear text", "get attribute",
}


class BrowserGuard(Hook):
    """Pre-probe (rf-mcp pre-validation style) + timeout injection, executed in-process via the
    Browser library instance (no RF keyword logging, invisible to the step record)."""

    name = "guard"

    def __init__(self, fast_timeout: Optional[str] = None, probe: bool = True, settle: float = 1.0) -> None:
        self.fast_timeout = fast_timeout
        self.probe = probe
        self.settle = settle

    def _lib(self):
        try:
            return BuiltIn().get_library_instance("Browser")
        except Exception:
            return None

    def pre(self, step: StepCtx) -> Optional[Dict[str, Any]]:
        if step.owner != "Browser" or step.name.lower() not in _BROWSER_LOCATOR_KWS or not step.args:
            return None
        lib = self._lib()
        if lib is None:
            return None
        t0 = time.perf_counter()
        if self.probe:
            sel = BuiltIn().replace_variables(step.args[0])
            count = None
            t_end = time.monotonic() + self.settle
            while True:
                try:
                    count = lib.get_element_count(sel)
                except Exception as e:  # invalid selector etc.
                    return {"cls": "INVALID_SELECTOR", "selector": sel, "error": str(e).splitlines()[0][:300],
                            "probe_ms": round((time.perf_counter() - t0) * 1000)}
                if count or time.monotonic() > t_end:
                    break
                time.sleep(0.1)
            step.extra["probe"] = {"count": count, "ms": round((time.perf_counter() - t0) * 1000)}
            if count == 0:
                return {"cls": "NOT_FOUND", "selector": sel, "count": 0, "probe_ms": step.extra["probe"]["ms"]}
            if count and count > 1:
                step.extra["probe"]["cls"] = "MULTI_MATCH"
        if self.fast_timeout:
            try:
                step.extra["old_timeout"] = lib.set_browser_timeout(self.fast_timeout)
            except Exception:
                pass
        return None

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        if "probe" in step.extra:
            rec["probe"] = step.extra["probe"]
        old = step.extra.get("old_timeout")
        if old is not None:
            lib = self._lib()
            if lib is not None:
                try:
                    lib.set_browser_timeout(old)
                except Exception:
                    pass


# ---------------------------------------------------------------- PlatynUI desktop safety
class DesktopSafety(Hook):
    """Reuses rf-mcp's stdlib-only safety classifier for PlatynUI interaction keywords."""

    name = "desktop"

    def __init__(self) -> None:
        self.error = None
        try:
            import importlib.util
            import pathlib
            import robotmcp  # type: ignore

            base = pathlib.Path(robotmcp.__file__).parent / "components" / "execution"
            mods = {}
            # load by file path: the package __init__ imports the whole rf-mcp executor stack
            for mod in ("desktop_display_safety", "platynui_focus"):
                spec = importlib.util.spec_from_file_location(f"_rfmcp_{mod}", base / f"{mod}.py")
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)  # type: ignore
                mods[mod] = m
            self._safety = mods["desktop_display_safety"]
            self._focus = mods["platynui_focus"]
        except Exception as e:
            self._safety = None
            self.error = repr(e)

    def pre(self, step: StepCtx) -> Optional[Dict[str, Any]]:
        if self._safety is None or not (step.owner or "").lower().startswith("platynui"):
            return None
        if not self._focus.is_interaction_keyword(step.name):
            return None

        class _S:  # session shim: per-session opt-ins live in helper config
            platynui_allow_active_desktop = False

        out = self._safety.evaluate_safety(_S())
        step.extra["desktop_safety"] = {k: out.get(k) for k in ("classification", "allowed", "bypassed")}
        if not out.get("allowed"):
            return {"cls": "DESKTOP_UNSAFE", "classification": out.get("classification"),
                    "reason": (out.get("reason") or "")[:400]}
        return None

    def post(self, step: StepCtx, rec: Dict[str, Any]) -> None:
        if "desktop_safety" in step.extra:
            rec["desktop_safety"] = step.extra["desktop_safety"]


def build_hooks(names: List[str], fast_timeout: Optional[str] = None) -> List[Hook]:
    hooks: List[Hook] = []
    for n in names:
        if n == "redact":
            hooks.append(Redactor())
        elif n == "hints":
            hooks.append(Hints())
        elif n == "guard":
            hooks.append(BrowserGuard(fast_timeout=fast_timeout))
        elif n == "desktop":
            hooks.append(DesktopSafety())
    return hooks
