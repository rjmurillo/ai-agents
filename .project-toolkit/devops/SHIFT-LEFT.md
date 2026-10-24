# Shift-Left Validation Strategy

<!-- # taste-lint: ignore file-size, the job ownership table and latency baseline sit beside the hook and CI sections they correct -->

**Status**: Active
**Version**: 2.0
**Last Updated**: 2026-10-23

## Overview

Shift-left validation catches defects on the developer's machine instead of in
CI review cycles. This document describes the local runner, the git hooks that
invoke it, and which checks CI repeats.

ADR-042 replaced the PowerShell validation runner with Python. Every command
below is the current one; the PowerShell entry points named in version 1.0 of
this document (`Validate-PrePR.ps1`, `Validate-Session.ps1`,
`Invoke-PesterTests.ps1`, `Validate-PathNormalization.ps1`,
`Validate-PlanningArtifacts.ps1`, `Detect-AgentDrift.ps1`) no longer exist.

## Unified Validation Runner

`scripts/validation/pre_pr.py` runs the full local gate sequence.

```bash
# Full validation
uv run --frozen python scripts/validation/pre_pr.py

# Skip the four quick-skippable gates
uv run --frozen python scripts/validation/pre_pr.py --quick
```

`--quick`, `--markdown-lint-only`, `--compact`, and `--summary-json` are the
flags. The runner reads every argument it declares.

`--compact` prints only the gates that did not pass. A gate that passes, or that
the pre-push fast stage already ran, prints nothing. Any other skip, and every
failing gate, keeps its own output (file and line), name, and verdict. A gate still running after 30 seconds prints one `[SLOW]` line with its
name, so a job that Lefthook kills at its timeout still leaves the hung gate's name
in the log. A child process a gate starts writes to the terminal directly, so its
output can print above that gate's `=== name ===` header. The pre-push
`pre-pr-validation` job passes `--compact`.

`--quick` skips YAML Style Validation, Path Normalization, Planning Artifacts,
and Agent Drift Detection. Measured 2026-08-19, those four gates cost 1.89s of
a 103.25s run, so `--quick` now saves under 2 percent. It was worth 50 to 90
seconds when the sequence had six gates; it is not a meaningful lever today.
Run the full sequence.

`--skip-tests`, its `SKIP_TESTS` environment default, and `--verbose` are gone.
All three were parsed and never read: no gate in `_SEQUENCE` set `skip_flag`,
and nothing read `verbose`. `--skip-tests` also described a Pester stage in a
repository tracking zero `.ps1` files. Passing any of them now fails with
argparse exit code 2 rather than being silently accepted.

## Validation Sequence

The ordered gate list is `_SEQUENCE` in `scripts/validation/pre_pr_sequence.py`.
Read it there. This document deliberately keeps no second copy: version 1.0
carried a six-row table that drifted from the real sequence for months without
anything detecting it.

To list the current gates:

```bash
uv run --frozen python -c "
import sys; sys.path.insert(0, 'scripts/validation')
from pre_pr_sequence import _SEQUENCE
for gate in _SEQUENCE: print(gate.name)
"
```

57 gates as of 2026-08-19.

### Cost distribution

Measured 2026-08-19 on a 4-CPU container against a tree with no changes
against `origin/main`. Most gates scale with the diff, so treat these as the
floor, not a forecast:

| Gate | Wall |
|------|-----:|
| Count Ratchets | 38.37s |
| Skill Markdown Portability | 16.07s |
| Subprocess Encoding Convention | 7.06s |
| Unreachable Code Detection | 5.83s |
| Documented Interpreter Portability | 4.53s |
| Python Syntax (compile gate) | 3.71s |
| Remaining 51 gates | 27.68s |
| **Total** | **103.25s** |

Thirty-five of the 57 gates finish in under 0.5s each.

YAML Style Validation reported 0.00s because `yamllint` was absent from the
measuring container and the gate returns early with a warning when the binary
is missing. Its real cost is unmeasured here.

Re-measure with:

```bash
SKIP_AUTOFIX=1 uv run --frozen python scripts/validation/pre_pr.py
```

The per-gate durations print in the Detailed Results block at the end.

## Evidence States

Since issue #5635 a gate reports one of five typed states rather than a boolean,
defined in `scripts/validation/evidence.py`. The distinction the boolean could
not carry is between a check that ran and one that only appeared to.

| State | Meaning | Blocks the push |
|-------|---------|-----------------|
| PASS | Ran against the named revision and scope, and proved the contract | No |
| FAIL | Ran, and found a violation | Yes |
| SKIP | Intentionally did not apply | No, by the exception below |
| BLOCKED | Could not run: a dependency or service was unavailable | Yes |
| UNKNOWN | Evidence incomplete, malformed, stale, or truncated | Yes |

Every non-PASS state carries a machine-readable reason code (`base_ref.unresolved`,
`diff.failed`, `script.absent`, `tool.absent`, `timeout`, `output.malformed`,
`aggregate.no_outcomes`, and the rest are constants in `evidence.py`), and the runner prints it next to
the gate name. A PASS must name the revision and the scope it ran against, so
the state cannot be reached without the proof it claims.

The gate accepts PASS and nothing else, with three declared exceptions in
`default_pre_pr_policy()`.

The first licenses SKIP for every gate. That is not new policy, it is this
document's prior sentence made executable: ADR-042 expunged the PowerShell
validators, so a downstream install legitimately lacks scripts this repository
ships, and `--quick` plus the pre-push fast stage skip gates on purpose.

The other two license BLOCKED, each for one named validator on the single
reason code `tool.absent`: `validate_workflow_yaml` when actionlint is not on
PATH, and `validate_yaml_style` when yamllint is not. Both tools are optional
developer-machine installs rather than repository dependencies, and neither
gate blocked on their absence before the typed states existed; the licences
make that prior behavior reviewable instead of implicit. The BLOCKED state is
still recorded and still printed, and since issue #5646 the RESULT line names
the licensed rows too, so a degraded run and a clean one are distinguishable.

UNKNOWN gets no exception at all, and BLOCKED gets none outside those two named
pairs. Correction, 2026-09-07: the paragraph this replaces claimed one exception
and that BLOCKED got none. Both halves were false when they shipped in PR #5641,
against the same function they described (issue #5646 item 4).

Add an exception only through `PolicyException`, which requires a written
justification so a reviewer can evaluate it.

### Boundary cases the states must not smooth over

Three cases sit where a plausible reading collapses two states into one. Each
is pinned by a test rather than left to the reader, because each one was wrong
in the first draft of this contract and was caught in review of PR #5641.

- **A run with no outcomes blocks.** `aggregate` reports UNKNOWN with
  `aggregate.no_outcomes`. A sequence that executed no gate examined nothing
  and so proved nothing. Before the reason was wired, the empty rejected list
  left `blocking` False and the runner exited 0, reporting a clean run of zero
  gates: the contract's own fail-open, reached through the aggregate instead of
  through a validator.
- **Applicability outranks tool absence.** A checkout with no
  `.github/workflows` reports SKIP `tree.absent` whether or not actionlint is
  installed. Probing the tool first told a downstream install holding neither
  to go install actionlint for a gate that did not apply to it.
- **An advisory gate still separates a finding from a failure.**
  `validate_yaml_style` tolerates yamllint findings and returns PASS, but a
  timeout returns UNKNOWN `timeout` and a failed exec returns BLOCKED
  `tool.absent`. A tool that never finished produced no findings, which is not
  the same as having found nothing.

## Exit Codes

The worst state that blocked the gate picks the code
(`evidence.py:exit_code_for`).

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Nothing blocked | All gates passed or were licensed by the policy |
| 1 | FAIL or UNKNOWN | Fix the violation, or read the gate's output |
| 2 | Config error | Bad repository root, or a SKIP the policy refused |
| 3 | BLOCKED | Install or authenticate the dependency the reason names |

## Machine-readable summary

`--summary-json PATH` (or `PRE_PR_SUMMARY_JSON`) writes the run as JSON: the
parent state, the counts per state, the declared policy, one row per gate with
its state, reason code, scope, revision, and counts, and the subset that
blocked.

```bash
uv run --frozen python scripts/validation/pre_pr.py --summary-json /tmp/pre-pr.json
```

## Unmigrated validators

The migration is deliberately partial. A gate that still returns `bool` is
adapted by `evidence.coerce_outcome`, which tags its failing side with the
reason code `legacy.boolean_contract` and its passing side with the scope
`whole validator (unmigrated boolean contract)`. Both are greppable in the JSON
summary, so the remaining work is countable rather than invisible.

Migrated so far: `checks_tooling.validate_session_end`,
`checks_tooling.validate_workflow_yaml`, `checks_tooling.validate_yaml_style`,
and `checks_mypy.validate_mypy_changed_files`.

Known unmigrated, verified on this tree:

- `checks_plugin.validate_workflow_local_run` returns `True` on four
  not-checked conditions: an unresolved base ref, a failed `git diff`, and the
  child script's exit 3 (tools unavailable) and exit 4 (auth unavailable).
- Three `checks_spec` gates return `True` when their child script is absent,
  printing a warning instead of raising `MissingScriptSkip`, so the skip is
  invisible to the runner.
- `checks_coverage.validate_review_marker` returns `True` on an advisory
  failure and rewrites the child's `[FAIL]` tokens to `[WARN]` to match. That
  one is a deliberate advisory (issue #1938), not a fail-open, but it still
  reports PASS for a check that found something.

All four are tracked in #5635.

The capability probes under `scripts/eval/` are a deliberate exception rather
than unmigrated work. `_harness_capability.py` already carries its own typed
contract from #5630 (`CapabilityStatus` with `VERIFIED`/`UNSUPPORTED`/
`UNVERIFIED`, a separate `EvidenceKind`, and worst-wins aggregation over an
explicit precedence tuple), and its vocabulary answers a different question:
whether a harness supports a capability, not whether a gate proved a contract.
`evidence.py` borrowed its shape. Collapsing the two would lose the
evidence-kind distinction that makes only backend evidence able to support
`VERIFIED`.

## Integration with Workflows

### Pre-commit hook

Lefthook filters staged files and runs the pre-commit jobs declared in
`lefthook.yml` (47 jobs at `0e98cb2d12`, 2026-10-23). Consult that file for the current
list rather than maintaining a second checklist here.

### Pre-push hook

`lefthook.yml` declares 27 pre-push jobs (`0e98cb2d12`, 2026-10-23), staged so
cheap gates fail before expensive ones start (issue #5066). The hook is `piped: true`, so a failing
job or group skips everything after it. Stage order:

1. Singleton guards: `repair-packed-refs`, `mutation-safety`,
   `push-ref-staleness`.
2. Fast stage, stdin half: a piped group of cheap ref-payload policies.
3. Fast stage, parallel half: ratchets and policy gates. The slowest job is
   `count-ratchets`, 40.2s at p50 on 2026-10-23 (see Latency baseline).
4. `security-scan` (semgrep), a serialized stdin consumer. Measured 6.7s for a
   7-file push.
5. Expensive stage: `python-tests`, `pre-pr-validation`, mypy,
   `workflow-local-run`, the CLI e2e smokes, and the advisory reporters.

On a 4-CPU container, `python-tests` took 475s across four serial partitions
(bulk 257.9s, mutation 166.6s, safe-push 36.9s, pr-autofix 8.8s) in an earlier
measurement. On the 48-CPU host in the Latency baseline below, `python-tests`
took 53s at p50 and `pre-pr-validation` took 220s. Which job dominates depends
on the host, so read the baseline before choosing what to reduce.

A job's standalone wall clock does not predict its wall clock inside the hook.
See `.claude/rules/ci-scripts.md` MUST-16 for the measured gap and why timeouts
must be sized against a real push.

### Failed hook output

`lefthook.yml` used to set `output: false`, so Lefthook printed a failed job's own
output and nothing else. It now sets `output: [failure]`, which lists each failed job.
`scripts/validation/lefthook_runner.py` hands `run <hook>` to
`scripts/validation/lefthook_failure_report.py`, which closes a failed run with a
block that names the hook, each failed job, and the command that reruns it:

```text
lefthook_runner: pre-commit FAILED (exit 1)
  job: python-format
  rerun: uv run --frozen lefthook run pre-commit --job python-format
  rerun hook: uv run --frozen lefthook run pre-commit
```

The job's own output comes first and keeps its file and line. A passing hook
prints nothing. The report lists every failed job. A job rerun skips the jobs that
ran before it, and `pre-pr-validation` assumes the fast-stage jobs passed, so run
the `rerun hook` line before you push. A pre-push rerun starts with
`printf` because the hook reads its ref lines from stdin; without them the rerun
runs no job and exits 0. The report drops credentials from a remote URL
argument (`https://user:token@host` prints as `https://host`). Output streams as
Lefthook writes it. Setting `LEFTHOOK_OUTPUT` yourself turns the report off.

Measured at `68cf87ef34` (2026-10-23) with one planted failure per hook. Counts are
lines on stdout and stderr. The report for one failed job adds 4 lines:

| Hook and job | Lines before | Lines after | Stage named | Rerun command |
|---|---|---|---|---|
| pre-commit, `python-format` | 13 | 17 | no, then yes | no, then yes |
| pre-push, `pre-pr-validation` | 1007 | 76, then the report | no, then yes | no, then yes |

The before count for `pre-pr-validation` held 231 PASS, 110 RUNNING, and 17 SKIP
lines, and the failing gate's file and line sat at line 97. The pre-push
`python-tests` job still prints its whole pytest log on a failure (69459 lines
in one run at the same SHA). This change leaves it as it was.

### CI pipeline

No workflow runs `pre_pr.py`. CI repeats individual validators through
dedicated workflows instead:

| Local gate | CI workflow |
|------------|-------------|
| Count Ratchets | `pr-validation.yml` |
| `python-tests` | `pytest.yml` (5 parallel matrix partitions) |
| Path Normalization | `validate-paths.yml` |
| Planning Artifacts | `validate-planning-artifacts.yml` |
| Agent Drift Detection | `drift-detection.yml` |
| Generated Artifact Staleness | `validate-generated-agents.yml` |
| Rule Activation Coverage | `validate-rule-activation-coverage.yml` |
| Spec ID Uniqueness | `validate-spec-id-uniqueness.yml` |
| Vendor Portability | `validate-vendor-portability.yml` |
| Plugin Version Bump | `validate-plugin-version-bump.yml` |
| Hook Anchoring | `hook-contract-check.yml` |
| Memory index count ratchet | `pr-validation.yml` |

The Job ownership table below lists every check with no CI step found. The
checks earlier versions of this section called out still have none:
`security-scan` (semgrep, pre-push), and `memory-index`
(`scripts/validation/memory_index.py`) and `memory-tier`
(`scripts/validate_memory_tier.py`), both pre-commit since issue #5626 deleted
`memory-validation.yml`. A local bypass is the only place they are enforced.
CI runs the unindexed-memory count ratchet, not those two validators. Mypy has a
CI form: `Run Python Tests` runs `scripts/ci/mypy_ratchet.py` on changed
Python files, which is narrower than the pre-push `python-type-check` job.

### Job ownership table

Each row is one pre-commit or pre-push job in `lefthook.yml` at `0e98cb2d12`
(2026-10-23): 47 pre-commit jobs and 27 pre-push jobs. The `commit-msg` job
(`commit-message-policy`) and the `pre-merge-commit` jobs are not rows. The Hook
column names the owner. A job has one owner unless the Also runs at column says
otherwise.

The CI counterpart column names a check that runs the same validator or the
count form of it. "Required" means the check is in the required status checks
of ruleset 11104075 on `main`, read on 2026-10-23 with
`gh api repos/rjmurillo/ai-agents/rules/branches/main`. Those checks are:
Validate Path Normalization, Validate Generated Files, Validate PR, Validate PR
title, Analyze (actions), Analyze (python), Run Python Tests, Validate Plugin
Version Bump, and Check whole-tree count ratchets (blocking).

Validate Path Normalization and Validate Generated Files run their steps only
when a path filter matches the change, and report success otherwise
(`validate-paths.yml`, `validate-generated-agents.yml`). A "Required" row under
either is enforced only for changes inside that filter.

The same call lists a `pull_request` rule, a `non_fast_forward` rule, and a
`deletion` rule for the default branch. Rows cite those rules as "ruleset
11104075".

"None found" means a search of `.github/workflows` for the script name, and for
the subcommand when the script is `git_hook_policy.py`, returned no workflow
step that runs the check. It does not rule out coverage by a pytest test.

Scope is read from the job: `glob`, `staged files`, `push files`, `push range
(stdin)`, or `unscoped`. An unscoped job runs on every invocation of its hook.
The Security column marks jobs that handle secrets, suppressions, or security
review. `adjacent` marks a job that gates a security-relevant input or contains
a security gate.

| Hook | Job | Scope | Checks | Also runs at | Security | CI counterpart |
|---|---|---|---|---|---|---|
| pre-commit | `repo-health` | unscoped | core.bare and shared git config sanity | pre-push | no | Local state, no CI analogue |
| pre-commit | `repair-packed-refs` | unscoped | Repairs packed-refs damage in the local clone (writes) | pre-push | no | Local state, no CI analogue |
| pre-commit | `branch-policy` | unscoped | Blocks a commit on main or master | - | no | Required: ruleset 11104075 pull_request rule on the default branch |
| pre-commit | `branch-context-policy` | unscoped | Blocks when the branch contradicts today's session log | pre-push | no | None found |
| pre-commit | `push-lock-commit-guard` | unscoped | Push lock guard before a commit | - | no | Local state, no CI analogue |
| pre-commit | `markdown-autofix` | glob | Autofixes staged Markdown (writes) | - | no | None found |
| pre-commit | `markdown-check` | glob | Lints staged Markdown | - | no | None found |
| pre-commit | `root-hygiene-policy` | staged files | Root directory hygiene for staged paths | - | no | None found |
| pre-commit | `session-policy` | glob | Staged session log shape | - | no | None found |
| pre-commit | `staged-dash-policy` | glob | Em and en dash scan of staged files | - | no | None found (branch-wide twin runs at pre-push as dash-prohibition) |
| pre-commit | `action-pin-policy` | glob | Staged workflow action SHA pins | - | adjacent | Required: Validate Generated Files, step Validate GitHub Actions SHA Pinning |
| pre-commit | `root-scratch-policy` | staged files | Blocks a new scratch file at the repo root | - | no | None found |
| pre-commit | `conflict-marker-policy` | staged files | Conflict markers in staged files | - | no | Required: Validate PR, step Check for conflict markers (tracked files only) |
| pre-commit | `python-autofix` | glob | Ruff autofix on staged Python (writes) | - | no | None found |
| pre-commit | `python-check` | glob | Ruff check on staged Python | - | no | Required: Run Python Tests, step Run ruff ratchet (changed Python files) |
| pre-commit | `python-format` | glob | Ruff format check on staged Python | - | no | Required: Run Python Tests, step Run ruff format check (whole tree) |
| pre-commit | `workflow-validation` | glob | validate_workflows.py on staged workflows | - | no | Required: Validate PR, step Validate workflow YAML (whole tree) |
| pre-commit | `actionlint` | glob | actionlint on staged workflows | - | no | None found. pr-validation.yml records that actionlint stays out of CI on purpose |
| pre-commit | `yaml-advisory` | glob | yamllint on staged YAML, advisory | - | no | CI, not required: yaml-lint.yml |
| pre-commit | `skillforge` | glob | Skillforge policy on staged skills | - | no | None found |
| pre-commit | `skill-size` | glob | Skill size budget, staged only | - | no | None found |
| pre-commit | `colocated-skill-tests` | glob | No new colocated skill tests, staged only | - | no | None found |
| pre-commit | `agents-write-targets` | glob | No writes to legacy .agents paths | - | no | CI, not required: validate-vendor-portability.yml |
| pre-commit | `planning-advisory` | glob | Planning artifact advisory | - | no | CI, not required: validate-planning-artifacts.yml |
| pre-commit | `infrastructure-advisory` | glob | Flags infrastructure files that need security review, advisory | - | adjacent | None found |
| pre-commit | `adr-review-policy` | glob | ADR edits need the review record | - | no | None found |
| pre-commit | `taste-advisory` | glob | Taste lint report, blocks only if the lint cannot run | - | no | Required: Validate PR, step Run taste-lint error-count ratchet (count form) |
| pre-commit | `security-suppressions-staged` | glob | Security suppression markers in staged changes | pre-merge-commit | yes | Required: Run Python Tests, step Check security suppressions in diff (pull request, issue 4061) |
| pre-commit | `subprocess-encoding` | glob | Subprocess encoding convention | - | no | Required: Run Python Tests, step Run subprocess encoding count ratchet (whole tree), count form |
| pre-commit | `generate-mcp-config` | glob | Regenerates MCP config (writes) | - | no | Not mapped to one step. Required: Validate Generated Files requires job Build-all Staleness, step Build-all staleness check (REQ-003-005), which runs build_all.py --check |
| pre-commit | `stage-mcp-config` | glob | Stages regenerated MCP config | - | no | Not applicable, git staging |
| pre-commit | `generate-agents` | glob | Regenerates agent files (writes) | - | no | Not mapped to one step. Required: Validate Generated Files requires job Build-all Staleness, step Build-all staleness check (REQ-003-005), which runs build_all.py --check |
| pre-commit | `generate-agent-catalog` | glob | Regenerates the agent catalog (writes) | - | no | Not mapped to one step. Required: Validate Generated Files requires job Build-all Staleness, step Build-all staleness check (REQ-003-005), which runs build_all.py --check |
| pre-commit | `stage-generated-agents` | glob | Stages regenerated agent files | - | no | Not applicable, git staging |
| pre-commit | `memory-token-update` | glob | Updates memory index token counts (writes) | - | no | Required: Validate PR, step Run memory-index token ratchet (check form) |
| pre-commit | `stage-memory-index` | glob | Stages the regenerated memory index | - | no | Not applicable, git staging |
| pre-commit | `memory-size` | glob | Memory file size limits | - | no | None found |
| pre-commit | `memory-index` | glob | Memory index consistency, orphan ratchet | - | no | None found |
| pre-commit | `memory-token-counts` | glob | Memory index token counts are current | - | no | Required: Validate PR, step Run memory-index token ratchet (count form) |
| pre-commit | `memory-tier` | glob | Memory tier validation | - | no | None found |
| pre-commit | `memory-cross-reference` | glob | Memory cross references (writes) | - | no | None found |
| pre-commit | `stage-memory-cross-references` | glob | Stages memory cross reference edits | - | no | Not applicable, git staging |
| pre-commit | `memory-placement` | glob | Memory file placement | - | no | Required: Validate PR, step Run memory-placement check |
| pre-commit | `memory-skill-format` | glob | Skill format validation, staged only | - | no | None found |
| pre-commit | `extract-session-episodes` | glob | Extracts episodes from staged session logs | - | no | None found |
| pre-commit | `context-output-check` | staged files | Context output manifest is complete | pre-merge-commit | no | Required: Run Python Tests, step Check complete context-output manifest (blocking) |
| pre-commit | `github-bash-policy` | glob | Bash in GitHub skill scripts | - | no | None found |
| pre-push | `repo-health` | unscoped | core.bare and shared git config sanity | pre-commit | no | Local state, no CI analogue |
| pre-push | `repair-packed-refs` | unscoped | Repairs packed-refs damage in the local clone (writes) | pre-commit | no | Local state, no CI analogue |
| pre-push | `mutation-safety` | unscoped | Mutation workspace check | - | no | Local state, no CI analogue |
| pre-push | `push-ref-staleness` | push range (stdin) | Pushed ref staleness against the remote | - | no | Local state, no CI analogue |
| pre-push | `push-ref-policy` | push range (stdin) | Pushed ref policy, including a non-fast-forward check | - | no | Required: ruleset 11104075 non_fast_forward rule |
| pre-push | `security-suppression-policy` | push range (stdin) | Security suppression markers in the pushed range | - | yes | Required: Run Python Tests, step Check security suppressions in diff (pull request, issue 4061) |
| pre-push | `placeholder-identity` | push range (stdin) | Placeholder author identity in pushed commits | - | no | CI, not required: placeholder-identity-check.yml |
| pre-push | `count-ratchets` | unscoped | Ten count ratchets from one registry (checks_ratchet.py RATCHETS) | - | no | Required: Run Python Tests (steps Run ruff ratchet (changed Python files), Run ruff count ratchet (whole tree), Run subprocess encoding count ratchet (whole tree)) and Validate PR (steps Run taste-lint error-count ratchet, Run type-ignore count ratchet, Run unindexed-memory count ratchet, Run memory-index token ratchet, Run CLI exit contract ratchet, Run canonical citations count ratchet, Run merge-tree ratchet) |
| pre-push | `python-unreachable-statements` | unscoped | No statement after return, raise, continue, break | - | no | None found |
| pre-push | `path-normalization` | unscoped | Documentation path normalization | - | no | Required: Validate Path Normalization, step Validate documentation paths (same script) |
| pre-push | `planning-artifacts` | unscoped | Planning artifact validation | - | no | CI, not required: validate-planning-artifacts.yml |
| pre-push | `branch-context-policy` | unscoped | Blocks when the branch contradicts today's session log | pre-commit | no | None found |
| pre-push | `review-axis-drift` | unscoped | Review axis prompts match their source | - | no | Required: Validate Generated Files, step Review-axes drift check (REQ-008-03) |
| pre-push | `dash-prohibition` | unscoped | Em and en dash scan of the whole branch | - | no | None found |
| pre-push | `security-scan` | push range (stdin) | Semgrep on every pushed head | - | yes | None found |
| pre-push | `pre-pr-validation` | unscoped | Runs pre_pr.py, 115 gates in _SEQUENCE | - | adjacent | None found as an aggregate: no workflow runs pre_pr.py, and some gates have their own CI steps |
| pre-push | `worktree-gc-report` | unscoped | Reports stale registered worktrees, advisory | - | no | Local state, no CI analogue |
| pre-push | `branch-config-prune-report` | unscoped | Reports stale branch sections in .git/config, advisory | - | no | Local state, no CI analogue |
| pre-push | `python-tests` | unscoped | Pytest suite via git_hook_policy pytest | - | no | Required: Run Python Tests, step Run pytest (partitioned matrix) |
| pre-push | `zero-collection-tests` | unscoped | Test files that collect zero tests | - | no | Required: Run Python Tests, step Check for zero-collection test files (blocking) |
| pre-push | `python-lint-advisory` | push files | Ruff on pushed Python, advisory | - | no | Required: Run Python Tests, step Run ruff ratchet (changed Python files) |
| pre-push | `python-type-check` | push files | Mypy on pushed Python | - | no | Required: Run Python Tests, step Run mypy ratchet (changed Python files) |
| pre-push | `workflow-local-run` | push files | Runs changed workflows locally with act | - | no | None found |
| pre-push | `additions-advisory` | unscoped | Branch additions against origin/main, advisory | - | no | None found |
| pre-push | `hook-anchoring-e2e` | push range (stdin) | Hook anchoring CLI smoke on hook file changes | - | no | CI, not required: plugin-cli-smoke.yml (shares globs via cli_smoke_paths.py) |
| pre-push | `plugin-load-e2e` | push range (stdin) | Plugin load CLI smoke on plugin file changes | - | no | CI, not required: plugin-cli-smoke.yml (shares globs via cli_smoke_paths.py) |
| pre-push | `bot-cascade-advisory` | unscoped | Bot review cascade on the open PR, needs gh, advisory | - | no | None found |

### Checks that run at more than one boundary

Three jobs run at both hooks: `repo-health`, `repair-packed-refs`, and
`branch-context-policy`. Two pre-commit jobs, `security-suppressions-staged` and
`context-output-check`, also run in the `pre-merge-commit` hook so that merge
commits get the same check. Each costs under 0.3s per run (see the baseline
below). A commit can happen with no push, and a push can carry commits made in
another clone or worktree, so neither hook can rely on the other having run.
`branch-context-policy` also reads the session log, which can change between
the commit and the push.

`pre-push` job `pre-pr-validation` runs `pre_pr.py`, which holds 115 gates in
`_SEQUENCE` (`pre_pr_sequence.py`, 2026-10-23). Five gates carry
`already_run_by` and skip when the matching unconditional pre-push job passed:
`count-ratchets`, `python-unreachable-statements`, `dash-prohibition`,
`path-normalization`, and `planning-artifacts`. The `Review Axis Drift` gate
runs the same command as the `review-axis-drift` job
(`generate_pr_quality_prompts.py --dry-run`) and has no `already_run_by`.
`Colocated Skill Tests` wraps the script behind the pre-commit job
`colocated-skill-tests`. Neither repeat is removed by this change.

A required CI check repeats a local job, or a count form of it, when the CI
counterpart cell says `Required`. The repeat is deliberate: CI is the backstop for pushes that skip
local hooks, such as web edits and bot branches. Moving a local check to CI is
a separate decision per job and needs a PR that shows the CI check blocking a
failing case first.

### Latency baseline

Measured at `0e98cb2d12` (2026-10-23) with `scripts/metrics/gate_latency.py`,
20 repetitions per row, on one Linux host with 48 CPUs, Python 3.14.8, and
lefthook 2.2.2. Each repetition ran the whole hook, never `--job`. Pre-push
runs fed a stdin ref line for a scratch branch (`HEAD` against `HEAD~1`) and the
hook arguments `origin <url>`. The raw reports are in
`.project-toolkit/metrics/gate-latency-2026-10-23/`, one file per row.

`lefthook.yml` set `output: false` when the sampler ran, which hid the per-job summary the
sampler parses. Every run set `LEFTHOOK_OUTPUT=summary,success,failure` so jobs parse.
Without it the report has a hook wall clock and no per-job rows.

| Hook | Change class | n | Status | p50 s | p95 s | max s | Load range (48 CPUs) | Slowest jobs by p50 |
|---|---|---|---|---|---|---|---|---|
| pre-commit | markdown | 20 | complete 20 | 27.9 | 28.1 | 28.1 | 2.8 to 6.7 | `agents-write-targets` 24.0s; `markdown-autofix` 1.1s |
| pre-commit | python | 20 | complete 20 | 25.5 | 25.8 | 26.1 | 3.1 to 4.9 | `agents-write-targets` 23.8s; `subprocess-encoding` 13.2s |
| pre-commit | workflows | 20 | complete 20 | 25.5 | 25.8 | 26.2 | 2.8 to 5.8 | `agents-write-targets` 23.8s; `context-output-check` 0.9s |
| pre-push | markdown | 20 | complete 20 | 263.2 | 280.2 | 388.5 | 2.7 to 12.8 | `pre-pr-validation` 220.4s; `python-tests` 54.2s |
| pre-push | python | 20 | complete 20 | 263.3 | 265.6 | 266.2 | 2.6 to 6.4 | `pre-pr-validation` 220.3s; `python-tests` 53.1s |
| pre-push | workflows | 20 | complete 20 | 263.0 | 267.1 | 270.9 | 2.6 to 4.4 | `pre-pr-validation` 220.3s; `python-tests` 53.4s |

Load is the 1-minute load average sampled before and after each repetition.
Other agents shared the host. One pre-push markdown repetition reached load 12.8
and took 388.5s; the other 19 took 261.6s to 280.2s. All 120 repetitions
completed with exit 0 and no truncation. With n=20, p95 is the 19th value of 20.

What the numbers show:

- Pre-push costs 263s at p50 for all three classes. The unscoped jobs set the
  floor, so a one-line Markdown push pays the same as a Python push.
- `pre-pr-validation` takes 220s at p50, 84 percent of the pre-push wall clock.
  It starts after the `count-ratchets` group, so the critical path is the group
  plus that job.
- Pre-commit costs 25.5s to 27.9s at p50. `agents-write-targets` takes 23.8s to
  24.0s of that in all three classes, including a one-file Markdown change.
- The first repetition was within 1 percent of the median in every row, so
  the runs show no separate cold-start cost. No cold machine or cold `uv` cache
  was measured.

Exclusions:

- Change classes `none`, `skills`, and `hooks` were not sampled. Pre-push costs
  about 88 minutes per class at n=20.
- Every sampled input was clean and passed. Failing inputs, partial staging, and
  first or deleting pushes were not sampled.
- Diagnostic volume was not measured. Every sampled input passed, and every run set `LEFTHOOK_OUTPUT`, which overrides the `output` key in `lefthook.yml`. The Failed hook output section measures it for one planted failure per hook.
- The stdin ref line is a fixed one-commit range. A larger outgoing range is not
  covered.
- No row sets a budget. The p50 and p95 values above are the input for setting
  one.

The earlier n=2 baseline in `.project-toolkit/metrics/gate-latency-v0.7.0/` ran
on a 4-CPU host, so its figures do not compare with these.

### Latency after

Measured at `c5fc0f5bec` (2026-10-23), 36 commits after the baseline SHA `0e98cb2d12`, with
the same `scripts/metrics/gate_latency.py`, the same six rows, 20 repetitions per row, the
same host (48 CPUs, Python 3.14.8, lefthook 2.2.2), whole hooks, and
`LEFTHOOK_OUTPUT=summary,success,failure`. Pre-push runs fed one stdin ref line
(`HEAD` against `HEAD~1`) and the hook arguments `origin <url>`, as in the baseline. The
`lefthook.yml` group layout is the same at both SHAs. The raw reports are in
`.project-toolkit/metrics/gate-latency-after-2026-10-23/`, one file per row. All 120
repetitions exited 0 and none was truncated. Every row ran the same job names at both SHAs.

End to end, wall clock of the whole hook:

| Hook | Change class | n | Before p50 s | Before p95 s | Before max s | After p50 s | After p95 s | After max s | p50 change |
|---|---|---|---|---|---|---|---|---|---|
| pre-commit | markdown | 20 | 27.9 | 28.1 | 28.1 | 6.6 | 6.7 | 6.8 | -76% |
| pre-commit | python | 20 | 25.5 | 25.8 | 26.1 | 7.1 | 7.2 | 7.2 | -72% |
| pre-commit | workflows | 20 | 25.5 | 25.8 | 26.2 | 4.4 | 4.5 | 4.5 | -83% |
| pre-push | markdown | 20 | 263.2 | 280.2 | 388.5 | 135.7 | 149.9 | 153.8 | -48% |
| pre-push | python | 20 | 263.3 | 265.6 | 266.2 | 134.9 | 135.8 | 135.9 | -49% |
| pre-push | workflows | 20 | 263.0 | 267.1 | 270.9 | 134.7 | 140.0 | 143.4 | -49% |

p95 is the 19th value of 20. The baseline rows are copied from the Latency baseline above.

Host conditions during the after run. Load is the 1-minute load average before and after
each repetition. The last column counts 5-second samples in which a `git push`, `pytest`, or
`lefthook` process ran outside the sampler. Before each row, the driver waited for three
10-second polls with none running, and for the pre-push rows until the load average was under 8.

| Hook | Change class | Status | Load range before (48 CPUs) | Load range after | Samples with another push, pytest, or lefthook running |
|---|---|---|---|---|---|
| pre-commit | markdown | complete 20 | 2.8 to 6.7 | 4.2 to 65.0 | 0 of 27 (0%) |
| pre-commit | python | complete 20 | 3.1 to 4.9 | 6.6 to 24.9 | 0 of 28 (0%) |
| pre-commit | workflows | complete 20 | 2.8 to 5.8 | 5.0 to 6.8 | 0 of 18 (0%) |
| pre-push | markdown | complete 20 | 2.7 to 12.8 | 3.3 to 20.1 | 217 of 541 (40%) |
| pre-push | python | complete 20 | 2.6 to 6.4 | 3.1 to 5.4 | 1 of 532 (0%) |
| pre-push | workflows | complete 20 | 2.6 to 4.4 | 2.8 to 15.8 | 117 of 533 (22%) |

Other agents shared the host and pushed during the `markdown` and `workflows` pre-push rows.
Two pre-commit rows saw load averages of 25 and 65 from processes that were not a
push, pytest, or lefthook run; they are unidentified. Pre-commit wall clock stayed within
6.4s to 6.8s across the `markdown` row, including the repetitions at load 36 to 65. Pre-push
`python` had another pytest process in 1 of 532 samples and no other push.

Per stage. A stage is a top-level step of the piped hook in `lefthook.yml` order. A job is
its own stage. A piped group counts the sum of its jobs. A parallel group counts its slowest
job, because lefthook reports a parallel group as the sum of its members. That choice is
read from `lefthook.yml`, not measured, and the stage times add to the hook wall clock
within 0.13s in all 240 repetitions. Group numbers are lefthook's own labels.

| Hook | Change class | Stage | Before p50 s | Before p95 s | After p50 s | After p95 s |
|---|---|---|---|---|---|---|
| pre-commit | markdown | group (5), piped, 2 jobs | 2.13 | 2.18 | 2.17 | 2.20 |
| pre-commit | markdown | group (6), parallel | 24.0 | 24.2 | 2.67 | 2.80 |
| pre-commit | markdown | group (14), `context-output-check` | 0.94 | 0.95 | 0.94 | 0.95 |
| pre-commit | markdown | 5 serial guard jobs | 0.66 | 0.68 | 0.66 | 0.67 |
| pre-commit | python | group (6), parallel | 23.8 | 24.1 | 5.41 | 5.48 |
| pre-commit | python | group (14), `context-output-check` | 0.94 | 0.94 | 0.93 | 0.94 |
| pre-commit | python | 5 serial guard jobs | 0.66 | 0.67 | 0.66 | 0.67 |
| pre-commit | workflows | group (6), parallel | 23.8 | 24.1 | 2.71 | 2.84 |
| pre-commit | workflows | group (14), `context-output-check` | 0.93 | 0.94 | 0.93 | 0.94 |
| pre-commit | workflows | 5 serial guard jobs | 0.66 | 0.66 | 0.66 | 0.67 |

| Hook | Change class | Stage | Before p50 s | Before p95 s | After p50 s | After p95 s |
|---|---|---|---|---|---|---|
| pre-push | markdown | group (4), piped, 3 jobs | 1.17 | 1.37 | 1.19 | 1.33 |
| pre-push | markdown | group (5), parallel, 7 jobs | 40.5 | 41.3 | 28.6 | 31.4 |
| pre-push | markdown | group (7), parallel | 220.4 | 235.8 | 104.8 | 116.9 |
| pre-push | markdown | 4 guard jobs and `security-scan` | 1.18 | 1.24 | 1.20 | 1.49 |
| pre-push | python | group (4), piped, 3 jobs | 1.18 | 1.41 | 1.17 | 1.23 |
| pre-push | python | group (5), parallel, 7 jobs | 40.3 | 41.2 | 28.4 | 28.8 |
| pre-push | python | group (7), parallel | 220.4 | 222.9 | 103.9 | 104.7 |
| pre-push | python | 4 guard jobs and `security-scan` | 1.18 | 1.31 | 1.19 | 1.25 |
| pre-push | workflows | group (4), piped, 3 jobs | 1.18 | 1.39 | 1.16 | 1.24 |
| pre-push | workflows | group (5), parallel, 7 jobs | 40.2 | 40.6 | 28.4 | 28.9 |
| pre-push | workflows | group (7), parallel | 220.4 | 224.3 | 103.9 | 107.7 |
| pre-push | workflows | 4 guard jobs and `security-scan` | 1.20 | 1.25 | 1.18 | 1.23 |

Per job, for the five slowest jobs by baseline p50 in each row:

| Hook | Change class | Job | Before p50 / p95 s | After p50 / p95 s |
|---|---|---|---|---|
| pre-commit | markdown | `agents-write-targets` | 24.0 / 24.2 | 2.66 / 2.80 |
| pre-commit | markdown | `markdown-autofix` | 1.08 / 1.10 | 1.09 / 1.11 |
| pre-commit | markdown | `markdown-check` | 1.06 / 1.10 | 1.08 / 1.10 |
| pre-commit | markdown | `context-output-check` | 0.94 / 0.95 | 0.94 / 0.95 |
| pre-commit | markdown | `taste-advisory` | 0.30 / 0.32 | 0.31 / 0.32 |
| pre-commit | python | `agents-write-targets` | 23.8 / 24.1 | 2.66 / 2.84 |
| pre-commit | python | `subprocess-encoding` | 13.2 / 13.4 | 5.40 / 5.48 |
| pre-commit | python | `context-output-check` | 0.94 / 0.94 | 0.93 / 0.94 |
| pre-commit | python | `taste-advisory` | 0.33 / 0.35 | 0.32 / 0.34 |
| pre-commit | python | `security-suppressions-staged` | 0.27 / 0.30 | 0.27 / 0.29 |
| pre-commit | workflows | `agents-write-targets` | 23.8 / 24.1 | 2.71 / 2.84 |
| pre-commit | workflows | `context-output-check` | 0.93 / 0.94 | 0.93 / 0.94 |
| pre-commit | workflows | `yaml-advisory` | 0.40 / 0.43 | 0.41 / 0.43 |
| pre-commit | workflows | `taste-advisory` | 0.31 / 0.34 | 0.30 / 0.34 |
| pre-commit | workflows | `action-pin-policy` | 0.27 / 0.29 | 0.25 / 0.28 |

| Hook | Change class | Job | Before p50 / p95 s | After p50 / p95 s |
|---|---|---|---|---|
| pre-push | markdown | `pre-pr-validation` | 220.4 / 235.8 | 104.6 / 113.8 |
| pre-push | markdown | `python-tests` | 54.2 / 89.8 | 6.92 / 106.6 |
| pre-push | markdown | `count-ratchets` | 40.4 / 41.3 | 28.6 / 31.4 |
| pre-push | markdown | `zero-collection-tests` | 36.3 / 36.9 | 37.1 / 41.9 |
| pre-push | markdown | `python-unreachable-statements` | 17.0 / 17.4 | 17.3 / 19.2 |
| pre-push | python | `pre-pr-validation` | 220.3 / 222.9 | 103.9 / 104.7 |
| pre-push | python | `python-tests` | 53.1 / 60.5 | 6.74 / 7.11 |
| pre-push | python | `count-ratchets` | 40.2 / 41.2 | 28.4 / 28.8 |
| pre-push | python | `zero-collection-tests` | 36.1 / 36.8 | 36.9 / 37.0 |
| pre-push | python | `python-unreachable-statements` | 16.9 / 17.4 | 17.2 / 17.6 |
| pre-push | workflows | `pre-pr-validation` | 220.3 / 224.3 | 103.8 / 107.7 |
| pre-push | workflows | `python-tests` | 53.4 / 57.9 | 6.77 / 7.07 |
| pre-push | workflows | `count-ratchets` | 40.2 / 40.6 | 28.4 / 28.9 |
| pre-push | workflows | `zero-collection-tests` | 36.1 / 36.4 | 36.8 / 38.9 |
| pre-push | workflows | `python-unreachable-statements` | 16.9 / 17.1 | 17.2 / 17.8 |

What changed:

- Pre-push `pre-pr-validation` fell from 220.4s to 103.9s at p50 and is still the slowest
  job, 77 percent of the pre-push wall clock. `count-ratchets` fell from 40.2s to 28.4s. Those
  two set the critical path, so pre-push p50 fell from 263s to 135s in all three classes.
- Pre-commit `agents-write-targets` fell from 23.8s to 2.7s and `subprocess-encoding` from
  13.2s to 5.4s. Pre-commit p50 fell from 25.5s to 27.9s (by class) to 4.4s to 7.1s.
- `zero-collection-tests` (36.9s) is now the second-longest job in the parallel group that
  holds `pre-pr-validation`. `python-unreachable-statements` is flat at 17.2s.
- Two jobs slowed by more than 0.3s at p50. `dash-prohibition` went from 0.69s to 1.13s in
  the `python` row, and `zero-collection-tests` went up 0.7s to 0.9s in each row.
- The 36 commits between the two SHAs include the `perf(validation)` PRs #6864 to #6878. This
  measurement does not isolate which commit moved which row.

`python-tests` is not a like-for-like row. Its p50 fell from 53.1s to 6.7s, but it sits in
the parallel group behind `pre-pr-validation`, so it does not set the hook wall clock. The
after runs reused a warm `pytest-testmon` database, which selects the tests a push needs.
Two controls of 3 repetitions each, `python` class, removed the testmon database first:
at `c5fc0f5bec` the first repetition took 68.7s and the next two 6.7s; at `0e98cb2d12` all
three took 51.3s to 52.7s. So the drop is a difference between the two SHAs. This
measurement does not show why. Three of the 20 pre-push `markdown` repetitions (61.6s,
106.6s, 116.9s) had a slow `python-tests` while other agents ran pytest, which is the
p95 of that row. The control reports are in the same directory.

Exclusions:

- The baseline exclusions still hold. Change classes `none`, `skills`, and `hooks` were not
  sampled. Every input was clean and passed. Failing inputs, partial staging, and first or
  deleting pushes were not sampled. The stdin ref line is a fixed one-commit range.
- Diagnostic volume was not re-measured. `LEFTHOOK_OUTPUT` was set for every run, which
  overrides the `output` key in `lefthook.yml`, and the sampler ran the lefthook binary
  directly, not through the failure-report wrapper. The Failed hook output section has the
  one-failure counts.
- The host was not quiet. See the host conditions table. Pre-push `markdown` and `workflows`
  overlapped other agents' pushes, so their p95 and max values include contention. Pre-push
  `python` did not.
- The after rows reuse a warm testmon database. A fresh database costs one `python-tests`
  run of 68.7s at `c5fc0f5bec` (one control repetition).
- The sampler `scripts/metrics/gate_latency.py` is the committed one and ran unchanged.
  The driver that ran the six rows one after another, waited for the host to go quiet,
  and logged load every 5 seconds is not committed.
- No row sets a budget. The after values are inputs for choosing one.

### Developer workflow

```text
1. Make changes
2. Commit (pre-commit hook runs per-file checks)
3. Push (pre-push hook runs branch-wide validation)
4. Open the PR (CI runs the workflows above)
```

Running `pre_pr.py` by hand before pushing is optional; the pre-push hook runs
the same sequence. Run it by hand when you want the failure in seconds rather
than after the test suite.

## Workflow Validation

### actionlint

Scope actionlint to the workflow files, not the repository. A bare `actionlint`
with no path argument recursively scans every `.yml` and `.yaml` file,
including composite action definitions under `.github/actions/*/action.yml`.
actionlint validates workflow files only; it parses a composite `action.yml` as
if it were a workflow and emits false errors (missing `on:` and `jobs:` keys,
unexpected `runs:` and `inputs:`). Composite actions cannot be validated with
actionlint. Pass an explicit glob:

```bash
actionlint .github/workflows/*.yml
```

Do not pass the bare directory `.github/workflows/`: actionlint rejects a
directory argument with "is a directory". The automated toolchain
(`scripts/validation/pre_pr.py`, `scripts/validation/run_workflow_local_test.py`)
already globs correctly; this note keeps manual invocations aligned.

Installation:

```bash
brew install actionlint                                    # macOS
go install github.com/rhysd/actionlint/cmd/actionlint@latest  # Go
```

### validate_workflows.py

`scripts/validate_workflows.py` checks structure, SHA pinning, ADR-006 size
limits, and permissions. See [docs/WORKFLOW-VALIDATION.md](../../docs/WORKFLOW-VALIDATION.md)
for its full contract, exit codes, and error table.

### run_workflow_local_test.py

`scripts/validation/run_workflow_local_test.py` is the pre-push gate for
changed workflows. It runs three ordered stages and short-circuits on the
first failure:

1. `actionlint`: static analysis.
2. `gh act -n`: dry run of the job graph and step wiring.
3. `gh act`: real execution in Docker.

```bash
uv run --frozen python scripts/validation/run_workflow_local_test.py \
  --files .github/workflows/pytest.yml

# Lint plus dry-run tier only
uv run --frozen python scripts/validation/run_workflow_local_test.py \
  --files .github/workflows/pytest.yml --no-full
```

Missing tools yield exit 3 on a developer machine and in CI. Inside a managed
remote container the gap degrades to exit 0 with a logged warning, because the
tools cannot be provisioned there (issues #2548 and #3064).

## YAML Style

`yamllint` checks line length, indentation, trailing spaces, comment spacing,
and end-of-file newlines against `.yamllint.yml`. Findings warn; they never
fail a commit or a push. The gate returns early with a warning when `yamllint`
is not installed.

```bash
pip install yamllint
yamllint .
```

## Local Workflow Testing with act

`act` (nektos/act) runs GitHub Actions workflows locally in Docker, which
shortens the push-check-tweak cycle.

### Prerequisites

```bash
# Install act, either standalone or as the gh extension
gh extension install https://github.com/nektos/gh-act
brew install act

# Docker is required
docker info
```

`.actrc` in the repository root sets `catthehacker/ubuntu:full-latest` images
for production parity (about 18GB), artifact storage in `.artifacts/`, caching
in `.cache/`, linux/amd64 architecture, and maps `windows-latest` to
`-self-hosted` so it runs on the host.

### Usage

```bash
# Through the repository wrapper
uv run --frozen python .claude/skills/github/scripts/test_workflow_locally.py \
  --workflow validate-paths --dry-run

# Direct act invocation
act pull_request -W .github/workflows/validate-paths.yml -n
act -l
```

Workflows requiring Copilot CLI or `BOT_PAT` cannot run locally and must rely
on CI feedback.

### Troubleshooting act

| Problem | Cause | Solution |
|---------|-------|----------|
| `act: command not found` | act not installed | Install via brew or the gh extension |
| `Cannot connect to Docker daemon` | Docker not running | Start Docker |
| `Error: image not found` | Missing image | `docker pull catthehacker/ubuntu:act-latest` |
| `Permission denied` | Docker socket permissions | Add the user to the docker group |
| `Workflow validation failed` | Workflow syntax error | Run actionlint first |
| `Unknown runner label` | Invalid `runs-on` | Use official runner labels |

act uses Linux containers, so Windows-specific path, line-ending, and
case-sensitivity behavior differs. Use `-P windows-latest=-self-hosted` to run
on the host.

## Troubleshooting

**Runner exits 2**: an environment fault. Confirm Python 3.14 through `uv`,
Node.js for markdownlint, and that the working directory is inside the
repository.

**Runner exits 1**: a gate failed. The Detailed Results block names the gate;
run that gate's script directly for the full output.

**A count ratchet fails right after `origin/main` moved**: merge or rebase onto
a freshly fetched `main` and re-measure before hunting the violation. See
`.claude/rules/ci-scripts.md` item 14.

## Related Documentation

- **Session log mechanics**: `.claude/rules/session-logs.md`
- **Git hook configuration**: `lefthook.yml`
- **Workflow validation**: [docs/WORKFLOW-VALIDATION.md](../../docs/WORKFLOW-VALIDATION.md)
- **CI script rules**: `.claude/rules/ci-scripts.md`
- **DevOps patterns**: `.project-toolkit/devops/validation-runner-pattern.md`

## References

- **Issue #325**: Unified shift-left validation runner
- **Issue #5066**: Pre-push fast-fail staging
- **ADR-006**: Thin workflows, testable modules
- **ADR-035**: Exit code standardization
- **ADR-042**: Python migration strategy (supersedes ADR-005)
