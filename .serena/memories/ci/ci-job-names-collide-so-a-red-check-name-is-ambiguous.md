# Job Names Collide, So a Red Check Name Does Not Identify the Failure

## The contradiction

Conventional reading: a failing check name tells you what broke. `gh pr checks`
prints one name per row, so the name looks like an identifier.

It is not. GitHub reports the **job name**, and job names are not unique across
workflows in this repository. Twelve display names are shared by two or more job
definitions.

## The case that costs the most

```
'Validate budget': 2 defs, both on pull_request
    instruction-budget.yml       :: validate-budget
    passive-context-budget.yml   :: validate-budget
```

These measure different corpora with different validators and the same byte
unit.
`instruction-budget.yml` runs `scripts.validation.instruction_budget`, which
reads `.github/instructions/*.instructions.md` and scores only the rules whose
`applyTo` glob is universal for a language (`is_language_universal`), in **bytes
per language extension** against `DEFAULT_CEILINGS_BYTES`.
`passive-context-budget.yml` runs `scripts/validate_workspace_budget.py` over
`AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, and
`.github/copilot-instructions.md`, in **bytes** against the root-layer
accepted-state ratchets.

A red row reading `Validate budget` says neither which workflow nor which
corpus, and editing the wrong one costs a full push and CI cycle to learn
nothing.

## Two kinds of collision

**Same name, mutually exclusive jobs.** `YAML Lint` (`lint` and `skip-lint`),
`Validate Skillbook`, and `Run Python Tests` declare one name on jobs whose
`if:` conditions are complements, so at most one can fail. That pattern keeps
a required check present when the path filter skips the real work. Both jobs
still appear in `gh run view`, one `success` and one `skipped`.

**Same name, jobs that both run.** The complement is not guaranteed:

```
agent-drift-detection.yml  check-paths    if: <none>          <- always runs
                           validate / bypass-warning / skip    (one of three)
```

`Agent Drift Detection` names four jobs, and `check-paths` always runs alongside
whichever of the other three fires. Do not assume a duplicated name means one
row is a skip shim.

**Cross-workflow reuse.** Different workflows, different subsystems, same name,
both able to run and to fail:

| Name | Defs | Workflows |
|---|---|---|
| `Check Changed Paths` | 9 | ai-spec-validation, cli-smoke, codeql-analysis, pytest, skillbook-validation, validate-paths, validate-plugin-manifests, validate-plugin-version-bump, yaml-lint |
| `Detect changes` | 5 | citation-verify, memory-health, memory-validation, passive-context-budget, skill-passive-compliance |
| `Validate budget` | 2 | instruction-budget, passive-context-budget |
| `Validate Investigation Claims` | 2 | ai-session-protocol, investigation-claim-backstop |
| `Debounce Workflow` | 2 | ai-pr-quality-gate, ai-spec-validation |

## What to do instead

Resolve the name to a run before acting. The `link` field carries the run and
job id, and the job id is the last path segment:

```bash
job=$(gh pr checks <N> --json name,state,link \
  -q '.[]|select(.state=="FAILURE")|.link' | head -1 | sed 's#.*/job/##')
gh run view --job "$job"                    # header names the workflow
gh run view --job "$job" --log-failed | tail -25
```

`gh run view --job` prints the workflow name in its header, so the ambiguity
resolves without reading a log. Grepping for the display name is cheaper but
only lists candidates; it cannot say which one is red on your PR:

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
        if isinstance(j, dict): n[j.get("name", jid)].append((p.name, jid))
for k, v in sorted(n.items()):
    if len(v) > 1: print(k, v)
'
```

Measured 2026-08-11 on the issue #4880 branch: **159 job definitions produce
135 unique display names.** Twelve names are used by more than one definition.
Count definitions, not names: the two numbers differ by 24 and are easy to
conflate. Jobs without `name:` use their job ID as the display name.

## Required result contexts are now unique

Issue #4785 closed the load-bearing collision. AI PR Quality Gate emits the
required `AI Quality Gate Results` context. Session Protocol Validation emits
the separately required `Session Protocol Results` context. Both names have
repo-wide uniqueness tests and both are active in ruleset 11104075.

CodeQL integration retains the generic, non-required `Aggregate Results` name.

## Related

- [ci-a-red-check-on-your-pr-may-be-inherited-from-main](ci-a-red-check-on-your-pr-may-be-inherited-from-main.md).
  The inverse: two check names, one underlying bug, and the bug is not yours.
  This memory is one name over two systems; that one is one cause under two names.
- [ci-validate-pr-is-many-gates-only-some-read-the-body](ci-validate-pr-is-many-gates-only-some-read-the-body.md).
  The same trap one level down: within a job, a step name does not describe what
  the step does either. A bad PR description surfaces as `Enforce Blocking Issues`.
- [workspace-shared-checkout-is-a-stale-detached-head](../workspace/workspace-shared-checkout-is-a-stale-detached-head.md).
  Verify workflow facts against current `origin/main`, not the shared checkout.
