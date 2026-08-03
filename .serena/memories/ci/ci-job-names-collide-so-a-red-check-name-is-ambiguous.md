# Job Names Collide, So a Red Check Name Does Not Identify the Failure

## The contradiction

Conventional reading: a failing check name tells you what broke. `gh pr checks`
prints one name per row, so the name looks like an identifier.

It is not. GitHub reports the **job name**, and job names are not unique across
workflows in this repository. Twelve names are shared by two or more jobs, and
eleven of those run on `pull_request`.

## The case that costs the most

```
'Validate budget': 2 defs, both on pull_request
    instruction-budget.yml       :: validate-budget
    passive-context-budget.yml   :: validate-budget
```

These measure different corpora with different validators and different units.
`instruction-budget.yml` runs `scripts.validation.instruction_budget` over the
always-on `.github/instructions/*.instructions.md` set, scored in **bytes per
language extension** against `DEFAULT_CEILINGS_BYTES`.
`passive-context-budget.yml` runs `scripts/validation/passive_context_budget.py`
over per-file passive context (`AGENTS.md`, `CLAUDE.md`, `memory-index.md`),
scored in **tokens per file**. A red row reading `Validate budget` does not say
which. Editing the wrong corpus costs a full push and CI cycle to learn nothing.

## Two kinds of collision

**Benign: the run/skip shim.** `YAML Lint` (`lint` and `skip-lint`),
`Run Python Tests` (`test` and `skip-tests`), `Validate Skillbook`, and
`Agent Drift Detection` declare the same name on mutually exclusive jobs inside
one workflow, so the path filter guarantees only one reports. That pattern is
deliberate: it keeps a required check green-and-present when the filter skips it.

**Dangerous: cross-workflow reuse.** Different workflows, different subsystems,
same name, both able to run:

| Name | Defs | Workflows |
|---|---|---|
| `Check Changed Paths` | 9 | ai-spec-validation, cli-smoke, codeql-analysis, pytest, skillbook-validation, validate-paths, validate-plugin-manifests, validate-plugin-version-bump, yaml-lint |
| `Detect changes` | 5 | citation-verify, memory-health, memory-validation, passive-context-budget, skill-passive-compliance |
| `Aggregate Results` | 3 | ai-pr-quality-gate, ai-session-protocol, test-codeql-integration |
| `Validate budget` | 2 | instruction-budget, passive-context-budget |
| `Validate Investigation Claims` | 2 | ai-session-protocol, investigation-claim-backstop |
| `Debounce Workflow` | 2 | ai-pr-quality-gate, ai-spec-validation |

## What to do instead

Resolve the name to a run before acting. The `link` field carries the workflow and
job id:

```bash
gh pr checks <N> --json name,state,link \
  -q '.[]|select(.state=="FAILURE")|.name+" -> "+.link'
gh run view --job <job-id> --log-failed | tail -25
```

The log names the workflow, so the ambiguity resolves in one call. Grepping
`.github/workflows/` for the display name also works and is cheaper:

```bash
grep -rn "name: Validate budget" .github/workflows/
```

## Reproduce the scan

```bash
uv run --frozen python -c '
import yaml, pathlib, collections
n = collections.defaultdict(list)
for p in sorted(pathlib.Path(".github/workflows").glob("*.y*ml")):
    d = yaml.safe_load(p.read_text())
    if not isinstance(d, dict): continue
    for jid, j in (d.get("jobs") or {}).items():
        if isinstance(j, dict) and j.get("name"): n[j["name"]].append((p.name, jid))
for k, v in sorted(n.items()):
    if len(v) > 1: print(k, v)
'
```

Measured 2026-08-03 at `origin/main` `db5aab393`: 113 named jobs, 12 colliding
names.

## Related

- [ci-validate-pr-is-many-gates-only-some-read-the-body](ci-validate-pr-is-many-gates-only-some-read-the-body.md).
  The same trap one level down: within a job, a step name does not describe what
  the step does either. A bad PR description surfaces as `Enforce Blocking Issues`.
- [workspace-shared-checkout-is-a-stale-detached-head](../workspace/workspace-shared-checkout-is-a-stale-detached-head.md).
  Verify workflow facts against current `origin/main`, not the shared checkout.
