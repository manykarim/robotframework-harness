"""rf-mcp step listener for a stock `robotcode repl --plain` session (experiment).

Works two ways:
  * CLI listener   - robot.toml:  listeners = { "rfmcp_listener.RfmcpListener" = [] }  (or --listener)
  * library listener - at the REPL:  Import Library    ${CURDIR}/rfmcp_listener.py
    (module name == class name convention is not used; the module exposes
     `rfmcp_listener` class below so `Import Library  rfmcp_listener.py` works).

Writes JSON lines to $RFMCP_JSONL (default ./.rf/steps.jsonl):
  {"t":"ready", ...}                      listener registered
  {"t":"step", "seq":n, "id":..., ...}    one record per TOP-LEVEL REPL body item (tree inside)
  {"t":"done", "id":"<id>"}               the client's sentinel `Comment    rfmcp-done    <id>` ran
  {"t":"idle", "id":..., "n":k}           (hook mode) REPL is back at a fresh prompt

Hook mode (RFMCP_HOOK=1, default on): wraps the interpreter's `read_line` and
`set_last_result` (found via robot's LOGGER) to (1) emit an `idle` record when
the REPL waits for a fresh statement, (2) pick up `# rfmcp-step: <id>` comment
lines as step ids (comments are a no-op for the REPL and are NOT recorded by
`.save`), (3) capture the return value of every top-level keyword.
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from robot.output import LOGGER
from robot.running.context import EXECUTION_CONTEXTS

DONE_MARKER = "rfmcp-done"
STEP_COMMENT = "# rfmcp-step:"
END_COMMENT = "# rfmcp-end:"
STOP_ON_FAIL = os.environ.get("RFMCP_STOP_ON_FAIL", "1") == "1"
MAX_REPR = int(os.environ.get("RFMCP_MAX_REPR", "800"))
MAX_DEPTH = int(os.environ.get("RFMCP_MAX_DEPTH", "6"))
MSG_LEVELS = set(os.environ.get("RFMCP_MSG_LEVELS", "INFO,WARN,ERROR,FAIL").split(","))


def _short(value, limit=MAX_REPR):
    try:
        if hasattr(value, "status_code") and hasattr(value, "text"):  # requests.Response
            s = f"<Response [{value.status_code}]> {value.text}"
        elif isinstance(value, str):
            s = value
        else:
            s = repr(value)
    except Exception as e:  # pragma: no cover
        s = f"<unrepresentable {type(value).__name__}: {e}>"
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s) - limit})"


def _jsonable(value):
    try:
        json.dumps(value)
        if len(json.dumps(value)) <= MAX_REPR:
            return value
    except Exception:
        pass
    return _short(value)


class rfmcp_listener:  # noqa: N801  (module/library name == class name)
    ROBOT_LISTENER_API_VERSION = 3
    ROBOT_LIBRARY_SCOPE = "GLOBAL"

    _active = None  # one writer per process even if imported twice

    def __init__(self, jsonl=None, hook=None):
        self.ROBOT_LIBRARY_LISTENER = self
        if rfmcp_listener._active is not None:
            # second registration (e.g. CLI listener + Import Library): stay silent
            self._dup = True
            return
        rfmcp_listener._active = self
        self._dup = False
        self.path = Path(jsonl or os.environ.get("RFMCP_JSONL", ".rf/steps.jsonl")).absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()
        self.stack = []  # open nodes
        self.seq = 0
        self.step_id = None  # set from `# rfmcp-step:` comment (hook mode)
        self.pending = []  # hook mode: step records waiting for return value / idle
        self.idle_n = 0
        self.src = []
        self.skipped = []
        self.step_failed = False
        hook = os.environ.get("RFMCP_HOOK", "1") if hook is None else hook
        self.hooked = False
        if str(hook).lower() in ("1", "true", "yes"):
            self.hooked = self._install_hook()
        self._emit({"t": "ready", "pid": os.getpid(), "hooked": self.hooked, "path": str(self.path)})

    # ---------------------------------------------------------------- output
    def _emit(self, rec):
        rec.setdefault("ts", round(time.time(), 3))
        with self._lock:
            self._fh.write(json.dumps(rec, default=str) + "\n")
            self._fh.flush()

    # ---------------------------------------------------------------- hook
    def _install_hook(self):
        interp = None
        for lg in list(getattr(LOGGER, "_other_loggers", [])):
            interp = getattr(lg, "interpreter", None)
            if interp is not None:
                break
        if interp is None or not hasattr(interp, "read_line"):
            return False
        self.interp = interp
        orig_read_line = interp.read_line
        orig_set_last = interp.set_last_result
        me = self

        def read_line(prompt, *a, **kw):
            fresh = not kw.get("multiline_continuation", False)
            if fresh:
                me._flush_pending()
                me.idle_n += 1
                me._emit({"t": "idle", "n": me.idle_n, "id": me.step_id})
            while True:
                text = orig_read_line(prompt, *a, **kw)
                st = text.strip()
                if fresh and st.startswith(STEP_COMMENT):
                    me.step_id = st[len(STEP_COMMENT):].strip()
                    me.src, me.skipped, me.step_failed = [], [], False
                    me._emit({"t": "begin", "id": me.step_id})
                    # swallow the comment line: behave as if nothing was typed yet
                    continue
                if fresh and st.startswith(END_COMMENT):
                    eid = st[len(END_COMMENT):].strip()
                    me._flush_pending()
                    rec = {"t": "end", "id": eid, "src": "\n".join(me.src), "steps": me.seq}
                    if me.skipped:
                        rec["skipped_src"] = "\n".join(me.skipped)
                    me._emit(rec)
                    me.src, me.skipped, me.step_failed = [], [], False
                    continue
                if fresh and me.step_failed and STOP_ON_FAIL and me.step_id is not None:
                    # a statement of this cell failed: skip the rest of the cell
                    # (repl-server semantics) until the end marker arrives
                    me.skipped.append(text)
                    continue
                if st:
                    me.src.append(text)
                return text

        def set_last_result(result):
            if me.pending and me.pending[-1].get("type") == "KEYWORD" and "return" not in me.pending[-1]:
                me.pending[-1]["return"] = _short(result) if result is not None else None
            return orig_set_last(result)

        interp.read_line = read_line
        interp.set_last_result = set_last_result
        return True

    def _flush_pending(self):
        while self.pending:
            self._emit(self.pending.pop(0))

    # ---------------------------------------------------------------- tree
    def _start(self, data, result, kind=None):
        if self._dup:
            return
        top = not self.stack
        is_kw = kind == "KEYWORD"
        name = (result.name or "") if is_kw else ""
        owner = getattr(result, "owner", None) if is_kw else None
        if owner is not None and not isinstance(owner, str):
            owner = getattr(owner, "name", str(owner))
        args = list(getattr(data, "args", ()) or ()) if is_kw else []
        if top and is_kw and getattr(result, "full_name", None) == "BuiltIn.Comment" and args and args[0] == DONE_MARKER:
            self.stack.append({"_marker": args[1] if len(args) > 1 else None})
            return
        node = {
            "type": kind or getattr(result, "type", "KEYWORD"),
            "name": name,
            "owner": owner,
            "args": [str(a) for a in args],
            "assign": list(getattr(data, "assign", ()) or ()) if is_kw else [],
            "items": [],
            "msgs": [],
        }
        if kind == "FOR":
            node.update(flavor=getattr(data, "flavor", None), assign=list(data.assign), for_values=list(data.values))
        if kind == "ITERATION":
            node["name"] = ", ".join(f"{k}={_short(v, 80)}" for k, v in getattr(result, "assign", {}).items())
        if kind in ("IF_BRANCH", "TRY_BRANCH", "WHILE") and getattr(data, "condition", None):
            node["condition"] = data.condition
        if kind == "TRY_BRANCH":
            node["branch"] = getattr(result, "type", None)
            if getattr(data, "patterns", None):
                node["patterns"] = list(data.patterns)
        if kind == "VAR":
            node.update(name=getattr(data, "name", ""), value=[str(v) for v in getattr(data, "value", ())])
        self.stack.append(node)

    def _end(self, data, result):
        if self._dup or not self.stack:
            return
        node = self.stack.pop()
        if "_marker" in node:
            if not self.stack:
                self._flush_pending()
                self._emit({"t": "done", "id": node["_marker"]})
            return
        node["status"] = getattr(result, "status", None)
        msg = getattr(result, "message", "")
        if msg:
            node["message"] = msg
        try:
            node["elapsed_ms"] = round(result.elapsed_time.total_seconds() * 1000, 1)
        except Exception:
            pass
        if node["assign"] and node["type"] == "KEYWORD" and node["status"] == "PASS":
            node["values"] = self._assigned_values(node["assign"])
        if not node["items"]:
            del node["items"]
        if not node["msgs"]:
            del node["msgs"]
        if self.stack:
            parent = self.stack[-1]
            if "_marker" in parent:
                return
            if len(self.stack) < MAX_DEPTH:
                parent.setdefault("items", []).append(node)
            else:
                parent["truncated"] = parent.get("truncated", 0) + 1
            return
        # top-level body item finished -> one step record
        self.seq += 1
        node = {"t": "step", "seq": self.seq, "id": self.step_id, **node}
        if node["status"] == "FAIL":
            self.step_failed = True
        if self.hooked:
            self.pending.append(node)  # wait for set_last_result / idle
        else:
            self._emit(node)

    def _assigned_values(self, assign):
        out = {}
        ctx = EXECUTION_CONTEXTS.current
        if ctx is None:
            return out
        for a in assign:
            name = a.rstrip("=").strip()
            if len(name) < 4 or "[" in name:  # item assignment like ${d}[k]
                continue
            base = "${" + name[2:-1] + "}"
            try:
                out[name] = _jsonable(ctx.variables[base])
            except Exception as e:
                out[name] = f"<unavailable: {e}>"
        return out

    # ---------------------------------------------------------------- listener v3 API
    def start_keyword(self, data, result):
        self._start(data, result, "KEYWORD")

    def end_keyword(self, data, result):
        self._end(data, result)

    def start_for(self, data, result):
        self._start(data, result, "FOR")

    def end_for(self, data, result):
        self._end(data, result)

    def start_for_iteration(self, data, result):
        self._start(data, result, "ITERATION")

    def end_for_iteration(self, data, result):
        self._end(data, result)

    def start_while(self, data, result):
        self._start(data, result, "WHILE")

    def end_while(self, data, result):
        self._end(data, result)

    def start_while_iteration(self, data, result):
        self._start(data, result, "ITERATION")

    def end_while_iteration(self, data, result):
        self._end(data, result)

    def start_if(self, data, result):
        self._start(data, result, "IF/ELSE ROOT")

    def end_if(self, data, result):
        self._end(data, result)

    def start_if_branch(self, data, result):
        self._start(data, result, "IF_BRANCH")

    def end_if_branch(self, data, result):
        self._end(data, result)

    def start_try(self, data, result):
        self._start(data, result, "TRY/EXCEPT ROOT")

    def end_try(self, data, result):
        self._end(data, result)

    def start_try_branch(self, data, result):
        self._start(data, result, "TRY_BRANCH")

    def end_try_branch(self, data, result):
        self._end(data, result)

    def start_group(self, data, result):
        self._start(data, result, "GROUP")

    def end_group(self, data, result):
        self._end(data, result)

    def start_var(self, data, result):
        self._start(data, result, "VAR")

    def end_var(self, data, result):
        self._end(data, result)

    def start_return(self, data, result):
        self._start(data, result, "RETURN")

    def end_return(self, data, result):
        self._end(data, result)

    def start_break(self, data, result):
        self._start(data, result, "BREAK")

    def end_break(self, data, result):
        self._end(data, result)

    def start_continue(self, data, result):
        self._start(data, result, "CONTINUE")

    def end_continue(self, data, result):
        self._end(data, result)

    def start_error(self, data, result):
        self._start(data, result, "ERROR")

    def end_error(self, data, result):
        self._end(data, result)

    def log_message(self, message):
        if self._dup or not self.stack:
            return
        node = self.stack[-1]
        if "_marker" in node:
            return
        lvl = message.level
        if lvl in MSG_LEVELS or (lvl == "TRACE" and message.message.startswith("Return: ")):
            if lvl == "TRACE":
                node["return"] = _short(message.message[8:])
                return
            node.setdefault("msgs", []).append(
                {"level": lvl, "html": bool(message.html), "text": _short(message.message, 400)}
            )

    def close(self):
        if not self._dup:
            self._flush_pending()
            self._emit({"t": "closed"})
