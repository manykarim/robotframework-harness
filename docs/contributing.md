# Contributing and releasing

## Development setup

```bash
uv sync --group dev                    # installer, runtime deps, tests
uv sync --group dev --group browser    # + Browser library for the simulation suite
uv run rfbrowser init --skip-browsers  # Browser node deps; browsers are reused from ~/.cache/ms-playwright
```

## Tests

| suite | command | notes |
|---|---|---|
| unit, installer, launcher, runtime, desktop, evidence | `uv run pytest -m "not browser" -q` | runs in CI on Linux, macOS and Windows |
| simulation (224 checks, real Browser sessions) | `uv run pytest tests/simulation -m browser -q` | Linux with chromium |
| evaluation harness (offline) | `uv run pytest tests/eval -q` | Linux only |
| evidence | `python3 evidence/check_claims.py --check-sources` | also in `evidence.yml` |
| docs | `uv run --group docs mkdocs build --strict` | also generates the CLI and environment references |

## Rules

- **The plugin tree `plugins/rf-harness/` is the single source of truth.** The wheel bundles it at build time.
- **Every `RFH_*` variable is registered in `src/rf_harness/config.py`**, with a default and a doc line. The docs build
  fails on undocumented variables or CLI flags.
- **The installer stays dependency-free**, Python 3.10+.
- **Behavior changes to the skill, hooks, feedback or runtime need a same-window A/B run** through the release gate
  (`eval/gate.py`). See [evaluation](concepts/evaluation.md).
- **Evidence:** new rounds go to `evidence/rounds/<NN>-<topic>/`. Run `evidence/scrub.py` before adding files, and
  update `claims.yaml` for every new published number.

## Release

1. Bump the version in `src/rf_harness/__init__.py`, `plugins/rf-harness/.claude-plugin/plugin.json` and
   `.claude-plugin/marketplace.json`. `scripts/check_versions.py` enforces that they match.
2. Run the release gate and archive its report as a new evidence round.
3. Tag `v<version>` and move `stable`. The release workflow then:
   - builds the wheel and sdist;
   - runs the scrub and claim checks;
   - publishes to PyPI (trusted publishing);
   - attaches the transcript assets to the GitHub release.
