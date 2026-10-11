## Purpose

Publishes all data and evidence behind the agent harness — every experiment round, its raw results, graders, reports and code — so that anyone can check, reproduce and challenge the published claims.

## ADDED Requirements

### Requirement: The archive contains every experiment round with its raw data

The repository SHALL contain an `evidence/` archive covering all research rounds from the rf-mcp research
(robotcode capability spikes, rounds 1–7, the static-analysis study and the hook capability matrix). Each round SHALL
include:
- its findings report;
- the raw per-session result files;
- the generated reports and summaries;
- the scenario definitions and graders used;
- the harness version under test;
- the run configuration (agents, models, repetitions, dates).

Every archived result file MUST yield exactly the published numbers. It MUST be byte-identical to the original
except for documented scrub substitutions, and its checksum SHALL be recorded.

#### Scenario: a round can be audited

- **WHEN** a reader opens the round-7 folder
- **THEN** it contains `findings_v31.md`, the result files for each run, their reports, the scenario and grader definitions, a configuration file naming the agents, models, repetitions and dates, and a checksum file matching the result files

### Requirement: Every published claim links to its data

The archive SHALL contain an index of claims. Each claim made in the README or documentation (for example "pooled pass
rate 0.83 vs 0.69") is listed with:
- the round;
- the result files;
- the analysis command that reproduces the number.

A check SHALL recompute the indexed numbers from the archived result files and fail when one differs.

#### Scenario: claim recomputation

- **WHEN** the evidence check runs the analysis command for the "pooled pass rate" claim
- **THEN** it reproduces 0.83 and 0.69 from the archived round-7 result files, or the check fails

### Requirement: Invalid and excluded data are documented, not hidden

The archive SHALL keep the records of excluded sessions and their exclusion reasons, separate from the scored data. It
SHALL also keep the incident notes:
- expired logins;
- exhausted provider credits;
- backend outages;
- grader artifacts;
- stopped runs.

Reports SHALL state how many sessions were excluded and why.

#### Scenario: credit-exhaustion exclusions

- **WHEN** a reader looks at round 7
- **THEN** they find the 76 sessions excluded because of exhausted OpenRouter credits, the detection rule, and the backup of the original result files

### Requirement: Published evidence is scrubbed of secrets and personal data

Before anything enters the archive or a release asset, a scrub SHALL check for, and remove or redact:
- API keys and tokens of all supported providers;
- OAuth credentials;
- agent home directories and authentication files;
- e-mail addresses other than the author's public one;
- machine-specific absolute home paths (normalized to a placeholder).

The scrub MUST run in CI on every change to `evidence/`, and a finding MUST fail the build.

#### Scenario: a key in a transcript blocks publication

- **WHEN** a transcript archive contains a string matching an OpenRouter key pattern
- **THEN** the scrub reports the file and line, and the release asset is not built

### Requirement: Large artifacts ship as checksummed release assets

Session transcripts and other artifacts too large for git history SHALL be published as release assets, after the
scrub, with a manifest listing each file, its checksum and the result row it belongs to. The archive SHALL document how
to download and verify them.

#### Scenario: transcript verification

- **WHEN** a reader downloads the round-7 transcript asset and runs the documented verification command
- **THEN** every transcript's checksum matches the manifest, and each maps to one result row

### Requirement: Experiments are reproducible from the archive

The archive SHALL document how to rerun each round:
- prerequisites;
- agent and model versions;
- the evaluation harness commands;
- expected cost and duration;
- how live-site drift affects comparability.

It SHALL state that only same-window comparisons are valid.

#### Scenario: rerunning round 7

- **WHEN** a contributor follows the round-7 reproduction guide with the documented agents
- **THEN** the evaluation harness runs the same scenario and arm matrix, and the report shows the same table layout as the archived report
