"""v3.1 output profiles (STDLIB ONLY; imported by hook.py): which output format a session gets.

Round-6 same-day A/B (findings_v3main.md): v3's lean output was best for Claude (0.65, cheapest) and fine for Codex, but
OpenCode/MiniMax M2.5 did better with v2's richer output (0.55 vs 0.40). v3.1 therefore picks a profile per session:

  lean  v3 behaviour and budgets (leanfmt): Claude 250/700, Codex 250/700 chars (success/failure)
  rich  v2-like guidance with v3's correctness fixes (richfmt): controls list after navigation, up to 8 nearest
        controls + keyword signature/first doc sentence + failure-type hint on EVERY failure, NEXT:, ~1,200 chars

Selection (first match wins):
  1. RFH32_PROFILE=lean|rich (explicit)
  2. the model id, from: RFH32_MODEL; the hook payload (model / model_id / modelID, or {providerID, modelID});
     ANTHROPIC_MODEL (Claude Code, e.g. OpenRouter routing); OPENCODE_MODEL; CODEX_MODEL; the model remembered from an
     earlier event of the session (OpenCode plugin: `opencode run -m`, chat.message); the agent transcript
     (transcript_path: last assistant "model"); Codex: $CODEX_HOME/config.toml `model = ...`
       anthropic/*, claude-*, haiku/sonnet/opus, OpenAI/Codex GPT models (gpt-*, o1/o3/o4..., codex, luna) -> lean
       MiniMax, DeepSeek, Qwen, GLM/Z.ai, Gemini, Kimi/Moonshot and every unknown model                   -> rich
  3. no model id at all: the agent's own vendor default -- claude, codex, copilot -> lean; opencode/other -> rich
The decision is stored in the session (.rf/hook32/session.json "profile") once it came from (1) or (2) and is logged
on every hook event (hook log: profile, profile_src, model).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROFILES = ("lean", "rich")
_LEAN_RX = re.compile(r"(^|[/:])anthropic/|claude|(^|[/\-_.])(haiku|sonnet|opus|fable)([\-_.\d]|$)|(^|[/:])openai/|"
                      r"(^|[/:\-])gpt[\-_.\d]|(^|[/:])(o\d)([\-_.]|$)|codex|chatgpt|(^|[\-/])luna\b", re.I)
_RICH_RX = re.compile(r"minimax|deepseek|qwen|glm|z-ai|zai-|zhipu|gemini|google/|kimi|moonshot", re.I)
AGENT_DEFAULT = {"claude": "lean", "codex": "lean", "copilot": "lean"}


def classify(model: Optional[str]) -> Tuple[Optional[str], str]:
    """model id -> (profile, family). None when there is no model id."""
    m = (model or "").strip()
    if not m:
        return None, ""
    fam = _RICH_RX.search(m)
    if fam:                    # explicit weak-model families first (e.g. "openrouter/qwen/..." or "minimax-...")
        return "rich", fam.group(0).lower().rstrip("/-")
    lean = _LEAN_RX.search(m)
    if lean:
        return "lean", ("anthropic" if re.search(r"anthropic|claude|haiku|sonnet|opus|fable", m, re.I) else "openai")
    return "rich", "unknown"


def _model_from_obj(v: Any) -> Optional[str]:
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        mid = v.get("modelID") or v.get("modelId") or v.get("id") or v.get("model") or v.get("name")
        prov = v.get("providerID") or v.get("providerId") or v.get("provider")
        if isinstance(mid, str) and mid:
            return f"{prov}/{mid}" if isinstance(prov, str) and prov and not mid.startswith(prov + "/") else mid
    return None


def model_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    for k in ("model", "model_id", "modelID", "modelId"):
        m = _model_from_obj(payload.get(k))
        if m:
            return m
    return None


_TR_MODEL = re.compile(r'"model"\s*:\s*"([^"]{2,120})"')


def model_from_transcript(path: Optional[str], tail_bytes: int = 262144) -> Optional[str]:
    """last "model": "<id>" in the agent transcript (Claude Code jsonl: assistant messages carry the model)."""
    if not path:
        return None
    try:
        p = Path(path)
        size = p.stat().st_size
        with p.open("rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    found = [m for m in _TR_MODEL.findall(data) if m not in ("<synthetic>",) and not m.startswith("<")]
    return found[-1] if found else None


def model_from_codex_config() -> Optional[str]:
    home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    try:
        text = (Path(home) / "config.toml").read_text()
    except OSError:
        return None
    m = re.search(r'(?m)^\s*model\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


def detect(agent: str, payload: Dict[str, Any], stored: Optional[Dict[str, Any]] = None,
           env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """-> {"profile", "src", "model", "family"}; src: env | model:<where> | default."""
    env = os.environ if env is None else env
    forced = (env.get("RFH32_PROFILE") or "").strip().lower()
    stored = stored or {}
    if forced in PROFILES:
        return {"profile": forced, "src": "env", "model": stored.get("model") or env.get("RFH32_MODEL"), "family": ""}
    model, where = None, ""
    for where, getter in (("RFH32_MODEL", lambda: env.get("RFH32_MODEL")),
                          ("payload", lambda: model_from_payload(payload)),
                          ("ANTHROPIC_MODEL", lambda: env.get("ANTHROPIC_MODEL") if agent == "claude" else None),
                          ("OPENCODE_MODEL", lambda: env.get("OPENCODE_MODEL")),
                          ("CODEX_MODEL", lambda: env.get("CODEX_MODEL") if agent == "codex" else None),
                          ("session", lambda: stored.get("model") if str(stored.get("src", "")).startswith("model")
                           else None),
                          ("transcript", lambda: model_from_transcript(payload.get("transcript_path"))),
                          ("codex-config", lambda: model_from_codex_config() if agent == "codex" else None)):
        try:
            model = getter()
        except Exception:
            model = None
        if model:
            break
    if model:
        prof, fam = classify(model)
        if where == "session":
            where = str(stored.get("src", "model:session")).split(":", 1)[-1]
        return {"profile": prof, "src": f"model:{where}", "model": model, "family": fam}
    return {"profile": AGENT_DEFAULT.get(agent, "rich"), "src": "default", "model": None, "family": ""}


def describe(info: Dict[str, Any]) -> str:
    return json.dumps({k: info.get(k) for k in ("profile", "src", "model", "family")})
