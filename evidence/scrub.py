#!/usr/bin/env python3
"""Scrub secrets and personal data out of evidence files (stdlib only).

    python3 evidence/scrub.py --check DIR [--report FILE]      # report findings, exit 1 if there are any
    python3 evidence/scrub.py --apply SRC DST [--report FILE]  # write a scrubbed copy of SRC (file or directory)

What it finds (rule names as they appear in reports):

    openrouter_key, openrouter_key_label, anthropic_key, openai_key, github_token, slack_token, aws_access_key,
    google_api_key, bearer_token, jwt, oauth_field, private_key  -- provider keys, tokens and credentials
    env_secret:<NAME>  -- the literal value of a secret environment variable. Names come from RFH_SCRUB_ENV
                          (comma-separated; default OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY,
                          GITHUB_TOKEN, MINIMAX_API_KEY). Values are read from the process environment and from
                          dotenv files (RFH_SCRUB_DOTENV, os.pathsep-separated; default ./.env and
                          ~/workspace/rf-mcp/.env when present); dotenv names ending in _KEY, _TOKEN, _SECRET or
                          _PASSWORD are included as well. Values are never printed.
    email              -- e-mail addresses outside the allowlist (ALLOWED_EMAILS, ALLOWED_EMAIL_DOMAINS)
    home_path          -- absolute home paths (/home/<user>, /Users/<user>, C:\\Users\\<user>) -> "~"
    home_slug          -- path-slug form of a home dir ("/-home-<user>-workspace-..." -> "/-home-~-workspace-...")
    auth_file          -- agent authentication files (auth.json, .credentials.json, credentials, .env, ...)
    agent_home         -- files inside an isolated agent home directory (agent_home/, .codex/, .copilot/, ...)

Text files are scanned as UTF-8 (undecodable bytes are kept as-is). ``*.gz`` files are decompressed in memory,
scanned, and in --apply written back gzip-compressed (mtime 0, so output is reproducible). Binary files are scanned
for key patterns only; a binary with a key cannot be redacted and is reported and not copied. Auth files and agent
homes are reported in --check and skipped in --apply.

Reports list rule, file and line, never the matched value. ``--report FILE`` writes the same data as JSON.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import io
import json
import os
import re
import shutil
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ENV_NAMES = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "MINIMAX_API_KEY")
DEFAULT_DOTENV = (".env", "~/workspace/rf-mcp/.env")
DOTENV_SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")
MIN_SECRET_LEN = 8

ALLOWED_EMAILS = frozenset({
    "many.kasiriha@gmail.com",             # the author's public address
    "manykarim@users.noreply.github.com",  # the author's GitHub no-reply address
    "noreply@anthropic.com",               # commit trailer of Claude Code
    "git@github.com",                      # ssh remote, not a person
    "me@x.org",                            # placeholder in the skill guides of the research prototypes
})
ALLOWED_EMAIL_DOMAINS = (
    "example.com", "example.org", "example.net", "example.invalid", "test.invalid",  # RFC 2606 fixtures
    "flowlinesupply.com",  # demo-shop accounts printed on the public demo site
    "beispiel.de",  # German placeholder domain; the car configurator's e-mail field shows "max@beispiel.de"
    "users.noreply.github.com",
)
# file extensions that look like TLDs in "name@2x.png"-style asset names
NOT_TLDS = frozenset({"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "js", "mjs", "css", "html", "htm", "json",
                      "py", "md", "txt", "robot", "resource", "ts", "map", "woff", "woff2", "ttf", "yaml", "yml",
                      "toml", "xml", "log", "gz", "zip", "lock",
                      # Python decorators such as "fn@wrapt.decorator" / "x@pytest.fixture"
                      "decorator", "fixture", "setter", "getter", "deleter", "property", "staticmethod",
                      "classmethod", "dataclass", "contextmanager", "wraps", "cache", "lru_cache", "mark",
                      # systemd unit names such as "user@1000.service" in cgroup paths
                      "service", "slice", "scope", "socket", "target", "mount", "timer", "device"})

AUTH_FILE_NAMES = frozenset({"auth.json", ".credentials.json", "credentials", "credentials.json", ".netrc",
                             ".git-credentials", "oauth_creds.json", ".env"})
AGENT_HOME_DIRS = frozenset({"agent_home", ".codex", ".copilot", ".claude-home", ".opencode-home"})

SKIP_DIRS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})  # local build caches
GZIP_SUFFIX = ".gz"
_NEWLINE = re.compile("\n")
BINARY_SNIFF = 8192


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    replacement: str | Callable[[re.Match[str]], str]
    kind: str  # secret | pii | path
    accept: Callable[[re.Match[str]], bool] | None = None  # False -> not a finding (allowlist / heuristics)
    binary: bool = False  # also scan binary files
    hints: tuple[str, ...] = ()  # fast pre-check: the rule can only match when one of these substrings occurs

    def applies(self, text: str) -> bool:
        return not self.hints or any(h in text for h in self.hints)

    def findings(self, text: str) -> Iterable[re.Match[str]]:
        if not self.applies(text):
            return
        for m in self.pattern.finditer(text):
            if self.accept is None or self.accept(m):
                yield m

    def substitute(self, text: str) -> tuple[str, int]:
        if not self.applies(text):
            return text, 0
        count = 0

        def repl(m: re.Match[str]) -> str:
            nonlocal count
            if self.accept is not None and not self.accept(m):
                return m.group(0)
            count += 1
            return self.replacement(m) if callable(self.replacement) else m.expand(self.replacement)

        return self.pattern.sub(repl, text), count


def _token(name: str) -> str:
    return f"[REDACTED:{name}]"


def _mixed_alnum(m: re.Match[str]) -> bool:
    """openai_key heuristic: a real key body has letters and digits."""
    body = m.group(0)[3:]
    return any(c.isdigit() for c in body) and any(c.isalpha() for c in body)


def _email_allowed(address: str) -> bool:
    a = address.lower()
    if a in ALLOWED_EMAILS:
        return True
    domain = a.rsplit("@", 1)[-1]
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_EMAIL_DOMAINS)


def _email_accept(m: re.Match[str]) -> bool:
    address = m.group(0)
    tld = address.rsplit(".", 1)[-1].lower()
    return tld not in NOT_TLDS and not _email_allowed(address)


def _keep_group(rule_name: str, group: int = 2) -> Callable[[re.Match[str]], str]:
    def repl(m: re.Match[str]) -> str:
        start, end = m.span(group)
        base = m.start(0)
        s = m.group(0)
        return s[: start - base] + _token(rule_name) + s[end - base:]

    return repl


_OAUTH_KEYS = r"(?:access_token|refresh_token|id_token|client_secret)"

STATIC_RULES: tuple[Rule, ...] = (
    Rule("private_key",
         re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----.*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----", re.S),
         _token("private_key"), "secret", binary=True, hints=("PRIVATE KEY-----",)),
    Rule("openrouter_key", re.compile(r"sk-or-v1-[0-9a-f]{20,}"), _token("openrouter_key"), "secret", binary=True,
         hints=("sk-or-v1-",)),
    Rule("openrouter_key_label", re.compile(r"sk-or-v1-[0-9a-f]{2,}\.{3}[0-9a-f]{2,}"),
         _token("openrouter_key_label"), "secret", hints=("sk-or-v1-",)),
    Rule("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), _token("anthropic_key"), "secret", binary=True,
         hints=("sk-ant-",)),
    Rule("openai_key", re.compile(r"(?<![A-Za-z0-9_\-])sk-(?!or-|ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"),
         _token("openai_key"), "secret", accept=_mixed_alnum, binary=True, hints=("sk-",)),
    Rule("github_token", re.compile(r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
         _token("github_token"), "secret", binary=True,
         hints=("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")),
    Rule("slack_token", re.compile(r"(?<![A-Za-z0-9])xox[abposr]-[A-Za-z0-9\-]{10,}"), _token("slack_token"),
         "secret", binary=True, hints=("xox",)),
    Rule("aws_access_key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
         _token("aws_access_key"), "secret", binary=True, hints=("AKIA", "ASIA")),
    Rule("google_api_key", re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{35}"), _token("google_api_key"),
         "secret", binary=True, hints=("AIza",)),
    Rule("jwt", re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
         _token("jwt"), "secret", binary=True, hints=("eyJ",)),
    Rule("bearer_token", re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9._~+/=\-]{24,})"),
         lambda m: m.group(1) + _token("bearer_token"), "secret", hints=("earer", "EARER")),
    # JSON ("key": "value"), JSON inside a JSON string (\"key\": \"value\"), and key=value / key: value forms
    Rule("oauth_field",
         re.compile(r"(" + _OAUTH_KEYS + r"(?:\\?[\"'])?\s*[:=]\s*(?:\\?[\"'])?)([A-Za-z0-9._~+/=\-]{16,})"),
         _keep_group("oauth_field"), "secret", hints=("_token", "client_secret")),
    Rule("email",
         re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
                    r"(?![A-Za-z0-9\-])"),
         _token("email"), "pii", accept=_email_accept, hints=("@",)),
    Rule("home_slug", re.compile(r"(?<=[/\\])-home-(?!~-)[A-Za-z0-9._]+-(?=[A-Za-z0-9])"), "-home-~-", "path",
         hints=("-home-",)),
    Rule("home_path",
         re.compile(r"(?<![\w~.\-])(?:/home/[A-Za-z0-9._\-]+|/Users/[A-Za-z0-9._\-]+|[A-Za-z]:(?:\\\\|\\)Users"
                    r"(?:\\\\|\\)[A-Za-z0-9._\-]+)(?=[/\\\"'\s:,;)\]}]|$)"),
         "~", "path", hints=("/home/", "/Users/", "Users\\")),
)


# --------------------------------------------------------------------------- #
# secret values from the environment (never printed)
# --------------------------------------------------------------------------- #
def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    return values


def secret_env_values(environ: dict[str, str] | None = None) -> dict[str, str]:
    """name -> literal secret value (process env + dotenv files). Values are only used for matching."""
    env = os.environ if environ is None else environ
    names = [n.strip() for n in env.get("RFH_SCRUB_ENV", ",".join(DEFAULT_ENV_NAMES)).split(",") if n.strip()]
    dotenv_spec = env.get("RFH_SCRUB_DOTENV")
    dotenv_paths = dotenv_spec.split(os.pathsep) if dotenv_spec else list(DEFAULT_DOTENV)
    found: dict[str, str] = {}
    for p in dotenv_paths:
        path = Path(p).expanduser()
        if not path.is_file():
            continue
        for name, value in _parse_dotenv(path).items():
            if name in names or name.upper().endswith(DOTENV_SECRET_SUFFIXES):
                if len(value) >= MIN_SECRET_LEN:
                    found.setdefault(name, value)
    for name in names:
        value = env.get(name, "")
        if len(value) >= MIN_SECRET_LEN:
            found[name] = value  # the process environment wins
    return found


def build_rules(environ: dict[str, str] | None = None) -> list[Rule]:
    rules: list[Rule] = []
    # literal values first and longest first, so the report names the variable
    for name, value in sorted(secret_env_values(environ).items(), key=lambda kv: -len(kv[1])):
        rules.append(Rule(f"env_secret:{name}", re.compile(re.escape(value)), _token(f"env:{name}"), "secret",
                          binary=True))
    rules.extend(STATIC_RULES)
    return rules


# --------------------------------------------------------------------------- #
# scanning
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    mode: str
    root: str
    files_scanned: int = 0
    files_changed: int = 0
    files_skipped: list[dict] = field(default_factory=list)  # auth files / agent homes / unredactable binaries
    rule_counts: Counter = field(default_factory=Counter)
    files: dict[str, Counter] = field(default_factory=dict)  # rel path -> rule -> count
    locations: list[dict] = field(default_factory=list)  # --check: {file, line, rule}
    max_locations: int = 2000

    def add(self, rel: str, rule: str, line: int | None = None, n: int = 1) -> None:
        self.rule_counts[rule] += n
        self.files.setdefault(rel, Counter())[rule] += n
        if line is not None and len(self.locations) < self.max_locations:
            self.locations.append({"file": rel, "line": line, "rule": rule})

    @property
    def findings(self) -> int:
        return sum(self.rule_counts.values()) + len(self.files_skipped)

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "root": self.root,
            "files_scanned": self.files_scanned,
            "files_changed": self.files_changed,
            "findings": self.findings,
            "rule_counts": dict(sorted(self.rule_counts.items())),
            "files_skipped": self.files_skipped,
            "files": {k: dict(sorted(v.items())) for k, v in sorted(self.files.items())},
            "locations": self.locations,
            "locations_truncated": sum(self.rule_counts.values()) > len(self.locations),
        }


def _is_binary(data: bytes) -> bool:
    head = data[:BINARY_SNIFF]
    if b"\x00" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as e:
        return e.start < len(head) - 4  # a multi-byte char cut at the sniff boundary is fine
    return False


def path_issue(rel_parts: tuple[str, ...]) -> str | None:
    """auth_file / agent_home for paths that must not be archived at all."""
    if not rel_parts:
        return None
    name = rel_parts[-1]
    base = name[: -len(GZIP_SUFFIX)] if name.endswith(GZIP_SUFFIX) else name
    if base in AUTH_FILE_NAMES:
        return "auth_file"
    if any(p in AGENT_HOME_DIRS for p in rel_parts[:-1]):
        return "agent_home"
    return None


def _line_of(text: str, pos: int, cache: list[int]) -> int:
    """1-based line number of pos; cache holds the newline offsets (built on first use)."""
    if not cache:
        cache.extend(m.start() for m in _NEWLINE.finditer(text))
        cache.append(len(text) + 1)
    return bisect.bisect_left(cache, pos) + 1


def scan_text(text: str, rules: list[Rule], rel: str, report: Report, binary: bool = False) -> None:
    nl: list[int] = []
    for rule in rules:
        if binary and not rule.binary:
            continue
        for m in rule.findings(text):
            report.add(rel, rule.name, _line_of(text, m.start(), nl))


def scrub_text(text: str, rules: list[Rule], rel: str, report: Report) -> str:
    for rule in rules:
        text, n = rule.substitute(text)
        if n:
            report.add(rel, rule.name, None, n)
    return text


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="surrogateescape")


def _encode(text: str) -> bytes:
    return text.encode("utf-8", errors="surrogateescape")


def read_payload(path: Path) -> tuple[bytes, bool]:
    """(decompressed bytes, was_gzip)."""
    raw = path.read_bytes()
    if path.name.endswith(GZIP_SUFFIX):
        try:
            return gzip.decompress(raw), True
        except (OSError, EOFError):
            return raw, False
    return raw, False


def gzip_bytes(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(data)
    return buf.getvalue()


def check_file(path: Path, rel: str, rules: list[Rule], report: Report) -> None:
    report.files_scanned += 1
    issue = path_issue(Path(rel).parts)
    if issue:
        report.files_skipped.append({"file": rel, "rule": issue})
    data, _ = read_payload(path)
    binary = _is_binary(data)
    scan_text(data.decode("latin-1") if binary else _decode(data), rules, rel, report, binary=binary)


def scrub_bytes(data: bytes, rel: str, rules: list[Rule], report: Report) -> bytes | None:
    """Scrubbed bytes, or None when the content cannot be published (binary with a secret)."""
    if _is_binary(data):
        probe = Report("probe", rel)
        scan_text(data.decode("latin-1"), rules, rel, probe, binary=True)
        if probe.rule_counts:
            for rule, n in probe.rule_counts.items():
                report.add(rel, rule, None, n)
            report.files_skipped.append({"file": rel, "rule": "binary_with_secret"})
            return None
        return data
    text = _decode(data)
    new = scrub_text(text, rules, rel, report)
    return data if new == text else _encode(new)


def apply_file(src: Path, dst: Path, rel: str, rules: list[Rule], report: Report) -> bool:
    """Write the scrubbed copy of src to dst. Returns False when the file was skipped."""
    report.files_scanned += 1
    issue = path_issue(Path(rel).parts)
    if issue:
        report.files_skipped.append({"file": rel, "rule": issue})
        return False
    data, was_gz = read_payload(src)
    out = scrub_bytes(data, rel, rules, report)
    if out is None:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if out is data:  # unchanged: copy the original bytes (keeps gzip members byte-identical)
        shutil.copyfile(src, dst)
        return True
    report.files_changed += 1
    dst.write_bytes(gzip_bytes(out) if was_gz else out)
    return True


def iter_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _rel(path: Path, root: Path) -> str:
    return path.name if root.is_file() else path.relative_to(root).as_posix()


def check_tree(root: Path, rules: list[Rule] | None = None, exclude: Iterable[str] = ()) -> Report:
    rules = build_rules() if rules is None else rules
    report = Report("check", root.as_posix())
    excl = tuple(exclude)
    for path in iter_files(root):
        rel = _rel(path, root)
        if any(rel == e or rel.startswith(e.rstrip("/") + "/") for e in excl):
            continue
        check_file(path, rel, rules, report)
    return report


def apply_tree(src: Path, dst: Path, rules: list[Rule] | None = None) -> Report:
    rules = build_rules() if rules is None else rules
    report = Report("apply", src.as_posix())
    for path in iter_files(src):
        rel = _rel(path, src)
        target = dst if src.is_file() else dst / rel
        apply_file(path, target, rel, rules, report)
    return report


def print_report(report: Report, out=None) -> None:
    out = out or sys.stdout
    r = report.to_json()
    print(f"scrub {r['mode']}: {r['files_scanned']} files scanned, {r['findings']} findings"
          + (f", {r['files_changed']} files changed" if r["mode"] == "apply" else ""), file=out)
    for rule, n in r["rule_counts"].items():
        print(f"  {rule}: {n}", file=out)
    for s in r["files_skipped"]:
        print(f"  skipped {s['file']} ({s['rule']})", file=out)
    if r["mode"] == "check":
        for loc in r["locations"][:200]:
            print(f"  {loc['file']}:{loc['line']}: {loc['rule']}", file=out)
        if len(r["locations"]) > 200:
            print(f"  ... {len(r['locations']) - 200} more locations in the JSON report", file=out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", metavar="DIR", help="report findings; exit 1 if there are any")
    g.add_argument("--apply", nargs=2, metavar=("SRC", "DST"), help="write a scrubbed copy of SRC to DST")
    ap.add_argument("--report", metavar="FILE", help="write the report as JSON (no secret values)")
    ap.add_argument("--exclude", action="append", default=[], metavar="REL",
                    help="--check: skip this path relative to DIR (repeatable)")
    args = ap.parse_args(argv)
    if args.check:
        root = Path(args.check)
        if not root.exists():
            ap.error(f"{root} does not exist")
        report = check_tree(root, exclude=args.exclude)
    else:
        src, dst = Path(args.apply[0]), Path(args.apply[1])
        if not src.exists():
            ap.error(f"{src} does not exist")
        report = apply_tree(src, dst)
    if args.report:
        Path(args.report).write_text(json.dumps(report.to_json(), indent=1) + "\n", encoding="utf-8")
    try:
        print_report(report)
    except BrokenPipeError:  # e.g. piped into head
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - silence the flush at exit
    if args.check:
        return 1 if report.findings else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
