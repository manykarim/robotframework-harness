# Static quality and refusals

## Static checks on every edit

The `lintd` helper analyzes each edited `.robot`/`.resource` file with the project's libraries and the live session in
scope:

- the **robotcode analyzer**, in-process: unknown keywords, argument errors, undefined variables, imports;
- a curated **Robocop agent profile**: only defects that make a suite fail or behave wrongly, plus outdated syntax.
  No documentation, naming, length or whitespace style rules.

Findings for variables or keywords that **exist in the live session** are dropped, such as a variable created with
`Set Test Variable`. That removed all dynamic-variable false positives in the research.

Together with `robot --dryrun`, robotcode analyze and the Robocop profile caught 32 of 33 planted errors in the
research corpus. See [static analysis](../../evidence/rounds/static-analysis/) and
[round 3](../../evidence/rounds/03-lsp-robocop/).

## The refusal policy

Over-refusing costs turns: v2 refused uncertain cases, and the agents lost turns arguing with it. So the harness
refuses an edit **only** when it would certainly do damage:

| refused | why |
|---|---|
| broken syntax or structure (`TokenError`, `ParsingError`, `InvalidHeader`, `ModelError`) | the file would not parse |
| deleting or renaming an existing test | repairs must fix tests, not remove them |
| hiding failures (ignoring errors around assertions, skip/non-critical tags on failing tests) | a green run would lie |
| installing packages or browsers into the environment | environment changes are the user's decision |

Everything else becomes a **one-line warning**, and the live run decides: unknown keyword, argument count, `-P` or
`PYTHONPATH` use, `Sleep`, fewer assertions, very large reads.

## Safe automatic fixes

Only deprecated-but-equivalent syntax is modernized, and each fix is reported to the agent:
- `Run Keyword If/Unless` → `IF`;
- `[Return]` → `RETURN`;
- `Exit/Continue For Loop` → `BREAK`/`CONTINUE`;
- `WITH NAME` → `AS`;
- `Force/Default Tags` → `Test Tags`;
- singular section headers;
- lowercase `else`.

Nothing is reformatted.

## Portability

The harness keeps suites runnable by plain `robot` without the harness:
- project libraries and resources are imported by path (`${CURDIR}/…`);
- the agent is warned about `-P`/`PYTHONPATH` workarounds;
- harness settings never go into your files.

## Configure

| variable | default | effect |
|---|---|---|
| `RFH_STATIC` | `on` | `runtime-only`: report only live results, keep only the certain structural refusals (set automatically next to rf-agentskills) |
| `RFH_RELAXED_DENIALS` | `1` | `0` restores the stricter v2 refusal policy (ablation) |
| `RFH_DENY_CODES` | `TokenError,ParsingError,InvalidHeader,ModelError` | analyzer codes that cause a refusal |
