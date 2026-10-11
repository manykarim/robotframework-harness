"""rf-harness hook launcher: find the project's Python and hand the hook event to ``rf_harness.runtime.hook``.

Every agent's hook configuration runs::

    python3 -S <plugin-or-install-dir>/bin/rfh-launch <Event> --agent <agent|auto> [--set RFH_NAME=value]...

with the agent's JSON payload on stdin. This module is stdlib only, runs on any Python 3.6+, and never fails:
a missing or incompatible runtime prints ONE setup hint on SessionStart and nothing otherwise, and every internal
error exits 0 (a crashing pre-tool hook denies the tool in Copilot CLI).

Interpreter order (design D3):
  1. ``RFH_PYTHON`` (authoritative: no fallback when it lacks the runtime),
  2. ``<project>/.rf/harness.json`` (written by ``rf-harness install``),
  3. ``VIRTUAL_ENV`` / ``CONDA_PREFIX``,
  4. ``<project>/.venv``,
  5. ``UV_PROJECT_ENVIRONMENT`` or the project's poetry environment (computed, no subprocess),
  6. ``python3`` on PATH.
The first interpreter whose site-packages hold ``robotframework_harness-<X.Y>.*.dist-info`` with the same major.minor
as ``LAUNCHER_VERSION`` and an ``rf_harness/runtime/hook.py`` wins. Nothing heavy is imported: venv site-packages are
scanned on disk; other interpreters report their ``sys.path`` once (cached per interpreter in the user cache dir).

Agent ``auto`` (the shared plugin hooks.json, read by Claude Code, Copilot CLI, VS Code and Codex) is resolved from
the environment, the parent processes and the payload. Copilot's SessionEnd is dropped (it fires after every run).
Identical events delivered twice within a few seconds (overlapping hook configurations) run once.
"""

import os
import sys
import time

LAUNCHER_VERSION = "0.9.0"
SETUP_COMMAND = "uvx robotframework-harness install --runtime-only"
RUNTIME_MODULE = "rf_harness.runtime.hook"
DIST_PREFIX = "robotframework_harness-"
AGENTS = ("claude", "codex", "copilot", "vscode", "opencode")
AGENT_ALIASES = {"claude-code": "claude", "copilot-cli": "copilot", "vs-code": "vscode"}
CANONICAL_EVENTS = {
    "sessionstart": "SessionStart",
    "userpromptsubmit": "UserPromptSubmit",
    "userpromptsubmitted": "UserPromptSubmit",
    "pretooluse": "PreToolUse",
    "posttooluse": "PostToolUse",
    "posttoolusefailure": "PostToolUseFailure",
    "stop": "Stop",
    "agentstop": "Stop",
    "sessionend": "SessionEnd",
}
VSCODE_TOOLS = frozenset((
    "create_file", "replace_string_in_file", "multi_replace_string_in_file", "insert_edit_into_file", "edit_file",
    "run_in_terminal", "read_file", "get_terminal_output", "manage_todo_list",
))
ANCESTOR_AGENTS = (("codex", "codex"), ("claude", "claude"), ("copilot", "copilot"), ("code", "vscode"),
                   ("code-insiders", "vscode"), ("opencode", "opencode"))
PIPE_SAFE_BYTES = 16000          # smallest default pipe buffer (macOS); larger payloads go through a temp file
DEDUPE_SECONDS = 5.0
TRACE_ENV = "RF_HARNESS_LAUNCH_TRACE"
DEDUPE_ENV = "RF_HARNESS_DEDUPE_S"
CACHE_ENV = "RF_HARNESS_CACHE_DIR"
IS_WINDOWS = os.name == "nt"


# ------------------------------------------------------------------------------------------------ JSON
# `import json` pulls in re/enum/functools/collections (~15 ms under -S, most of the launcher's own time); the C
# accelerator `_json` scans and encodes without them. Any problem falls back to the json module.
class _ScanContext:
    strict = True
    object_hook = None
    object_pairs_hook = None
    parse_float = float
    parse_int = int
    memo = {}

    @staticmethod
    def parse_constant(name):
        return {"NaN": float("nan"), "Infinity": float("inf"), "-Infinity": float("-inf")}[name]


_WS = " \t\n\r"
try:
    import _json

    _SCAN = _json.make_scanner(_ScanContext())
    _ENC = _json.encode_basestring_ascii
except Exception:  # pragma: no cover - e.g. PyPy
    _SCAN = _ENC = None


def loads(text):
    if _SCAN is not None:
        start = len(text) - len(text.lstrip(_WS))
        try:
            value, end = _SCAN(text, start)
        except Exception:
            value, end = None, -1
        if end >= 0 and not text[end:].strip(_WS):
            return value
    import json

    return json.loads(text)


def dumps(value):
    if _ENC is None:  # pragma: no cover
        import json

        return json.dumps(value)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _ENC(value)
    if isinstance(value, (int, float)):
        return repr(value) if value == value and value not in (float("inf"), float("-inf")) else "null"
    if isinstance(value, dict):
        return "{" + ", ".join(_ENC(str(k)) + ": " + dumps(v) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(dumps(v) for v in value) + "]"
    return _ENC(str(value))


# ------------------------------------------------------------------------------------------------ arguments / input
def parse_args(argv):
    """Return (event, agent, sets, rest). ``--set RFH_X=v`` is consumed here; unknown args go to the runtime."""
    event, agent, sets, rest = "", "auto", {}, []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--agent" and i + 1 < len(argv):
            agent = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--agent="):
            agent = arg.split("=", 1)[1]
            i += 1
            continue
        if arg == "--set" and i + 1 < len(argv):
            key, _, value = argv[i + 1].partition("=")
            if key.startswith("RFH_"):
                sets[key] = value
            i += 2
            continue
        if not event and not arg.startswith("-"):
            event = arg
        else:
            rest.append(arg)
        i += 1
    agent = (agent or "auto").strip().lower()
    return event, AGENT_ALIASES.get(agent, agent), sets, rest


def canonical_event(event):
    return CANONICAL_EVENTS.get(event.replace("_", "").replace("-", "").lower(), event)


def read_stdin():
    try:
        stream = sys.stdin
        if stream is None or stream.isatty():
            return b""
        return stream.buffer.read()
    except Exception:
        return b""


def parse_payload(data):
    if not data or not data.strip():
        return {}
    try:
        payload = loads(data.decode("utf-8", "replace"))
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


# ------------------------------------------------------------------------------------------------ agent detection
def ancestor_agent(max_depth=8):
    """Agent named by the nearest parent process (Linux /proc only; cheap file reads)."""
    if not os.path.isdir("/proc/self"):
        return None
    pid = os.getppid()
    for _ in range(max_depth):
        if pid <= 1:
            return None
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                parts = [p for p in fh.read().split(b"\0") if p][:2]
            with open(f"/proc/{pid}/stat", "rb") as fh:
                stat = fh.read()
        except OSError:
            return None
        names = [os.path.basename(p.decode("utf-8", "replace")).lower() for p in parts]
        for exe, agent in ANCESTOR_AGENTS:
            if any(n == exe or n == exe + ".exe" for n in names):
                return agent
        try:
            pid = int(stat[stat.rindex(b")") + 2:].split()[1])
        except (ValueError, IndexError):
            return None
    return None


def detect_agent(event, payload, environ, ancestry=None):
    """Concrete agent for ``--agent auto``: environment, then parent processes, then the payload shape."""
    if environ.get("COPILOT_CLI"):
        return "copilot"
    if environ.get("CLAUDECODE"):
        return "claude"
    if "turn_id" in payload:
        return "codex"
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool in VSCODE_TOOLS or (tool == "apply_patch" and "input" in tool_input) or "filePath" in tool_input:
        return "vscode"
    found = ancestry() if ancestry is not None else ancestor_agent()
    if found:
        return found
    if "model" in payload and "transcript_path" in payload:
        return "codex"
    if any(k.startswith("VSCODE_") for k in environ):
        return "vscode"
    if event[:1].islower():
        return "copilot"
    return "claude"


# ------------------------------------------------------------------------------------------------ project root
def _has_robot_files(directory, limit=4000):
    try:
        with os.scandir(directory) as it:
            for n, entry in enumerate(it):
                if n >= limit:
                    return False
                if entry.name.endswith(".robot"):
                    return True
    except OSError:
        return False
    return False


def project_root(start):
    """Nearest ancestor with .rf/, .git or pyproject.toml; else the nearest with *.robot files; else ``start``."""
    start = os.path.abspath(start)
    home = os.path.abspath(os.path.expanduser("~"))
    directory, robot_dir = start, None
    for _ in range(64):
        if (os.path.isdir(os.path.join(directory, ".rf")) or os.path.exists(os.path.join(directory, ".git"))
                or os.path.isfile(os.path.join(directory, "pyproject.toml"))):
            return directory
        if robot_dir is None and directory != home and _has_robot_files(directory):
            robot_dir = directory
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return robot_dir or start


def start_dir(payload):
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    if cwd and os.path.isdir(cwd):
        return cwd
    return os.getcwd()


# ------------------------------------------------------------------------------------------------ interpreters
def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = loads(fh.read())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def venv_python(prefix):
    if not prefix:
        return None
    names = (("Scripts", "python.exe"), ("python.exe",)) if IS_WINDOWS else (("bin", "python"), ("bin", "python3"))
    for parts in names:
        path = os.path.join(prefix, *parts)
        if os.path.isfile(path):
            return path
    return None


def _project_name(pyproject_text):
    import re

    for section in ("tool.poetry", "project"):
        match = re.search(r"^\[" + re.escape(section) + r"\]\s*$(.*?)(?=^\[|\Z)", pyproject_text, re.M | re.S)
        if match:
            name = re.search(r"""^name\s*=\s*["']([^"']+)["']""", match.group(1), re.M)
            if name:
                return name.group(1)
    return None


def poetry_virtualenvs_dir(environ):
    if environ.get("POETRY_VIRTUALENVS_PATH"):
        return environ["POETRY_VIRTUALENVS_PATH"]
    if environ.get("POETRY_CACHE_DIR"):
        return os.path.join(environ["POETRY_CACHE_DIR"], "virtualenvs")
    home = os.path.expanduser("~")
    if IS_WINDOWS:
        base = environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, "pypoetry", "Cache", "virtualenvs")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", "pypoetry", "virtualenvs")
    return os.path.join(environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"), "pypoetry", "virtualenvs")


def poetry_env_name(name, root):
    """Poetry's ``EnvManager.generate_env_name`` (name + 8 chars of the hashed project path)."""
    import base64
    import hashlib
    import re

    sanitized = re.sub(r'[ $`!*@"\\\r\n\t]', "_", name.lower())[:42]
    digest = hashlib.sha256(os.path.normcase(os.path.realpath(root)).encode("utf-8")).digest()
    return sanitized + "-" + base64.urlsafe_b64encode(digest).decode()[:8]


def poetry_python(root, environ):
    pyproject = os.path.join(root, "pyproject.toml")
    try:
        with open(pyproject, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    if "[tool.poetry" not in text and not os.path.isfile(os.path.join(root, "poetry.lock")):
        return None
    name = _project_name(text)
    base = poetry_virtualenvs_dir(environ)
    if not name or not os.path.isdir(base):
        return None
    prefix = poetry_env_name(name, root) + "-py"
    try:
        matches = sorted(e for e in os.listdir(base) if e.startswith(prefix))
    except OSError:
        return None
    for entry in reversed(matches):
        python = venv_python(os.path.join(base, entry))
        if python:
            return python
    return None


def path_python(environ):
    names = ("python.exe", "python3.exe") if IS_WINDOWS else ("python3",)
    for directory in (environ.get("PATH") or "").split(os.pathsep):
        for name in names:
            path = os.path.join(directory, name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def candidates(root, environ):
    """(source, python) pairs in the D3 order; RFH_PYTHON alone when set."""
    explicit = environ.get("RFH_PYTHON")
    if explicit:
        return [("RFH_PYTHON", explicit)]
    found = []
    harness = read_json(os.path.join(root, ".rf", "harness.json"))
    if isinstance(harness.get("python"), str):
        found.append(("harness.json", harness["python"]))
    for var in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        python = venv_python(environ.get(var))
        if python:
            found.append((var, python))
    python = venv_python(os.path.join(root, ".venv"))
    if python:
        found.append((".venv", python))
    uv_env = environ.get("UV_PROJECT_ENVIRONMENT")
    if uv_env:
        python = venv_python(uv_env if os.path.isabs(uv_env) else os.path.join(root, uv_env))
        if python:
            found.append(("UV_PROJECT_ENVIRONMENT", python))
    python = poetry_python(root, environ)
    if python:
        found.append(("poetry", python))
    python = path_python(environ)
    if python:
        found.append(("PATH", python))
    seen, unique = set(), []
    for source, python in found:
        key = os.path.normcase(os.path.abspath(python))
        if key not in seen:
            seen.add(key)
            unique.append((source, python))
    return unique


# ------------------------------------------------------------------------------------------------ runtime check
def _expand_pth(site_dir, dirs):
    try:
        names = sorted(n for n in os.listdir(site_dir) if n.endswith(".pth"))
    except OSError:
        return
    for name in names:
        try:
            with open(os.path.join(site_dir, name), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith(("#", "import ", "import\t")):
                        continue
                    path = line if os.path.isabs(line) else os.path.join(site_dir, line)
                    if os.path.isdir(path) and path not in dirs:
                        dirs.append(path)
        except OSError:
            continue


def static_site_dirs(python):
    """site-packages of a venv / conda interpreter, found on disk (plus path entries of its .pth files)."""
    prefix = os.path.dirname(os.path.dirname(os.path.abspath(python)))
    if IS_WINDOWS and not os.path.isfile(os.path.join(prefix, "pyvenv.cfg")):
        prefix = os.path.dirname(os.path.abspath(python))
    if not (os.path.isfile(os.path.join(prefix, "pyvenv.cfg")) or os.path.isdir(os.path.join(prefix, "conda-meta"))):
        return None
    dirs = []
    if IS_WINDOWS:
        candidates_ = [os.path.join(prefix, "Lib", "site-packages")]
    else:
        lib = os.path.join(prefix, "lib")
        try:
            candidates_ = [os.path.join(lib, n, "site-packages") for n in sorted(os.listdir(lib)) if n.startswith("python")]
        except OSError:
            candidates_ = []
    for site_dir in candidates_:
        if os.path.isdir(site_dir):
            dirs.append(site_dir)
    for site_dir in list(dirs):
        _expand_pth(site_dir, dirs)
    return dirs


def cache_dir(environ):
    if environ.get(CACHE_ENV):
        return environ[CACHE_ENV]
    home = os.path.expanduser("~")
    if IS_WINDOWS:
        return os.path.join(environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), "rf-harness")
    return os.path.join(environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"), "rf-harness")


def queried_sys_path(python, environ):
    """``sys.path`` reported by the interpreter itself, cached per interpreter path + mtime."""
    try:
        stamp = f"{os.path.abspath(python)}|{os.stat(python).st_mtime}"
    except OSError:
        return []
    cache_file = os.path.join(cache_dir(environ), "launch-paths.json")
    cache = read_json(cache_file)
    if isinstance(cache.get(stamp), list):
        return cache[stamp]
    import subprocess

    env = dict(environ)
    env.pop("PYTHONSTARTUP", None)
    try:
        proc = subprocess.Popen([python, "-c", "import sys,json;print(json.dumps([p for p in sys.path if p]))"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        out, _ = proc.communicate(timeout=5)
        paths = loads(out.decode("utf-8", "replace") or "[]")
    except Exception:
        return []
    if not isinstance(paths, list):
        return []
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        cache = {k: v for k, v in cache.items() if isinstance(v, list)}
        cache[stamp] = paths
        tmp = f"{cache_file}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(dumps(dict(list(cache.items())[-32:])))
        os.replace(tmp, cache_file)
    except OSError:
        pass
    return paths


def runtime_in(dirs):
    """(version or None, has_runtime_package) for a list of import directories."""
    version, has_runtime = None, False
    for directory in dirs:
        if not has_runtime and os.path.isfile(os.path.join(directory, "rf_harness", "runtime", "hook.py")):
            has_runtime = True
        if version is None:
            try:
                names = os.listdir(directory)
            except OSError:
                continue
            for name in names:
                if name.startswith(DIST_PREFIX) and name.endswith(".dist-info"):
                    version = name[len(DIST_PREFIX):-len(".dist-info")] or _metadata_version(directory, name)
                    break
    return version, has_runtime


def _metadata_version(directory, dist_info):
    try:
        with open(os.path.join(directory, dist_info, "METADATA"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
                if not line.strip():
                    break
    except OSError:
        pass
    return None


def compatible(version):
    return bool(version) and version.split(".")[:2] == LAUNCHER_VERSION.split(".")[:2]


def inspect_python(python, root, environ, harness):
    """Return (status, version) with status in ok | missing | incompatible | absent."""
    if not python or not os.path.isfile(python):
        return "absent", None
    dirs = static_site_dirs(python)
    version, has_runtime = runtime_in(dirs or [])
    if not (version and has_runtime):
        recorded = harness.get("site_packages") if harness.get("python") == python else None
        dirs = recorded if isinstance(recorded, list) and recorded else queried_sys_path(python, environ)
        version, has_runtime = runtime_in(dirs)
    if not (version and has_runtime):
        return "missing", version
    return ("ok" if compatible(version) else "incompatible"), version


def resolve(root, environ):
    """First compatible interpreter: (python, source, status, version). status is that of the best candidate."""
    harness = read_json(os.path.join(root, ".rf", "harness.json"))
    first = None
    for source, python in candidates(root, environ):
        status, version = inspect_python(python, root, environ, harness)
        if status == "ok":
            return python, source, status, version
        if first is None or (first[2] != "incompatible" and status == "incompatible"):
            first = (python, source, status, version)
    return first or (None, None, "missing", None)


# ------------------------------------------------------------------------------------------------ output / hand-off
def setup_hint(agent, status, python, version):
    where = f" ({python})" if python else ""
    if status == "incompatible":
        text = (f"[rfh] The Robot Framework harness runtime {version} in this project's Python environment{where} "
                f"does not match the plugin {LAUNCHER_VERSION}; the harness hooks are inactive until you run: "
                f"{SETUP_COMMAND}")
    else:
        text = (f"[rfh] The Robot Framework harness runtime is not installed in this project's Python environment"
                f"{where}; the harness hooks are inactive until you run: {SETUP_COMMAND}")
    if agent == "opencode":
        return {"action": "context", "text": text}
    if agent == "copilot":
        return {"additionalContext": text}
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def trace(environ, record):
    path = environ.get(TRACE_ENV)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(dumps(record) + "\n")
    except OSError:
        pass


def is_duplicate(event, agent, data, environ):
    """True when the same event + payload was already launched within DEDUPE_SECONDS."""
    try:
        window = float(environ.get(DEDUPE_ENV, DEDUPE_SECONDS))
    except ValueError:
        window = DEDUPE_SECONDS
    if window <= 0 or not data.strip():
        return False
    import zlib

    blob = f"{event}\0{agent}\0".encode() + data
    key = f"{zlib.crc32(blob):08x}{zlib.adler32(blob):08x}{len(blob):x}"
    directory = os.path.join(cache_dir(environ), "dedupe")
    path = os.path.join(directory, key)
    now = time.time()
    try:
        os.makedirs(directory, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        try:
            if now - os.stat(path).st_mtime < window:
                return True
            os.utime(path, None)
        except OSError:
            return False
        return False
    except OSError:
        return False
    if int(now * 1000) % 50 == 0:      # occasional cleanup of old markers
        try:
            for name in os.listdir(directory):
                stale = os.path.join(directory, name)
                if now - os.stat(stale).st_mtime > 60:
                    os.unlink(stale)
        except OSError:
            pass
    return False


def refeed_stdin(data):
    """Make ``data`` the next process's stdin (fd 0) before exec."""
    if len(data) <= PIPE_SAFE_BYTES:
        read_fd, write_fd = os.pipe()
        view = memoryview(data)
        while view:
            written = os.write(write_fd, view)
            view = view[written:]
        os.close(write_fd)
        os.dup2(read_fd, 0)
        os.close(read_fd)
        return
    import tempfile

    tmp = tempfile.TemporaryFile()
    tmp.write(data)
    tmp.flush()
    tmp.seek(0)
    os.dup2(tmp.fileno(), 0)


def hand_off(python, event, agent, rest, data, env):
    argv = [python, "-m", RUNTIME_MODULE, event, "--agent", agent] + list(rest)
    if IS_WINDOWS:              # no real exec on Windows: run, forward stdout and the exit code
        import subprocess

        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            code = subprocess.run(argv, input=data, env=env).returncode
        except OSError:
            return 0
        return code if code in (0, 2) else 0
    refeed_stdin(data)
    os.execve(python, argv, env)
    return 0   # pragma: no cover - execve does not return


def emit(obj):
    try:
        sys.stdout.write(dumps(obj) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def run(argv, environ=None):
    environ = dict(os.environ if environ is None else environ)
    started = time.time()
    event, agent, sets, rest = parse_args(argv)
    data = read_stdin()
    payload = parse_payload(data)
    canon = canonical_event(event)
    if agent not in AGENTS:
        agent = detect_agent(event, payload, environ)
    record = {"event": event, "agent": agent, "launcher": LAUNCHER_VERSION}
    if agent == "copilot" and canon == "SessionEnd":
        record.update(action="skip", reason="copilot fires SessionEnd after every run")
        trace(environ, record)
        return 0
    root = project_root(start_dir(payload))
    python, source, status, version = resolve(root, environ)
    record.update(root=root, python=python, source=source, status=status, version=version)
    if status != "ok":
        record["action"] = "hint" if canon == "SessionStart" else "skip"
        record["ms"] = round((time.time() - started) * 1000, 1)
        trace(environ, record)
        if canon == "SessionStart":
            emit(setup_hint(agent, status, python, version))
        return 0
    if is_duplicate(canon, agent, data, environ):
        record.update(action="skip", reason="duplicate delivery")
        trace(environ, record)
        return 0
    env = dict(environ)
    harness_env = read_json(os.path.join(root, ".rf", "harness.json")).get("env")
    if isinstance(harness_env, dict):
        for key, value in harness_env.items():
            if isinstance(key, str) and key.startswith("RFH_") and key not in env:
                env[key] = str(value)
    env.update(sets)
    record.update(action="exec", ms=round((time.time() - started) * 1000, 1))
    trace(environ, record)
    return hand_off(python, event, agent, rest, data, env)


def main(argv=None):
    code = 0
    try:
        code = run(sys.argv[1:] if argv is None else argv)
    except BaseException:  # noqa: B036 - the launcher must never fail a hook
        code = 0
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(code if code in (0, 2) else 0)


if __name__ == "__main__":
    main()
