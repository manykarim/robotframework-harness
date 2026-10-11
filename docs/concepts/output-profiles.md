# Output profiles

Different models need different amounts of feedback. Strong models do best with very short answers. Open-weight models
need more context in each answer. The harness picks a profile per session.

| | lean | rich |
|---|---|---|
| for | Claude, GPT / Codex models | MiniMax, DeepSeek, Qwen, GLM, Gemini, Kimi, unknown models |
| budget per answer | 250 chars on success, 700 on failure (OpenCode 600, `NEXT:` first) | 1,200 chars (`RFH_MAX_CTX_RICH`) |
| controls | ≤ 3 nearest on failure | ≤ 8 on failure; ≤ 8 after each navigation (form fields first) |
| keyword signature, hints | once per session | signature, first doc sentence and a type-specific hint on every failure |

Mandatory parts survive truncation in both profiles: the failing line, the error, the verdict, actual vs expected,
and `NEXT:`.

## How the profile is chosen

1. `RFH_PROFILE=lean|rich` forces it.
2. Otherwise the model id decides, from the hook payload, the agent's environment and configuration
   (`ANTHROPIC_MODEL`, `OPENCODE_MODEL`, Codex `config.toml`, …), or the session transcript.
3. With no model id, the agent's default applies: Claude Code, Codex and Copilot get lean; OpenCode gets rich.

The profile and where it came from are logged with every hook event (`.rf/hook/hooks.jsonl`).

## Evidence

In round 7 (same window, 206 valid sessions), the rich profile improved the open-weight models over the lean v3
output:
- OpenCode/MiniMax 0.47 → 0.53;
- GLM 0.75 → 0.88;
- Qwen 0.75 → 0.88;
- DeepSeek tied at 1.00.

Pooled, that is 0.68 → 0.78, not yet statistically significant (p = 0.45). Lean costs Claude and GPT nothing. The
profile was detected correctly in 70 of 70 sessions. See [round 7](../../evidence/rounds/07-v31-v32/).
