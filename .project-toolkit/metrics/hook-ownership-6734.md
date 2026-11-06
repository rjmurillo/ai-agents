---
type: metrics
id: hook-ownership-6734
title: Owner boundary for every pre-commit and pre-push job at d7ae505
epic: EPIC-5456
issue: 6734
created: 2026-10-20
status: draft
---

# Hook check ownership, d7ae505

Slice 2 of issue #6734 (owner decision 2026-10-20: option A). One row per leaf
job of `pre-commit` (47) and `pre-push` (27) in `lefthook.yml` at
`d7ae505961f1c03b834a4b8b219bc56fdb969841`, 74 in all, groups flattened. This is
a dated record, not a policy: `lefthook.yml` stays the only owner of what runs.
Nothing moves in this change. Latency figures come from
`.project-toolkit/metrics/hook-latency-6734.md`.

## How the owner is assigned

Each job gets exactly one owner boundary, by the first rule that fits, in this
order: guard, writer, advisory, CI-owned, local only.

| Kind | Rule | Owner |
|---|---|---|
| guard | Protects the local git action or local machine state (`.git/config`, push lock, pushed refs). CI never sees that state. | the hook it runs in |
| writer | Rewrites or stages content in the commit being made. Only a commit-time hook can do that. | pre-commit |
| advisory | Never blocks on findings. | the hook it runs in |
| CI-owned | A required CI context runs the same script or tool, in the same mode, over a superset of the content, with no path filter that can skip it. | required CI |
| local only | Anything else: no CI twin, a CI twin that is not a required check, a twin behind a path filter, or a twin whose equivalence is unproven. | the hook it runs in |

"Required" means one of the 9 contexts pinned in
`scripts/ci/ruleset_required_contexts.py` for ruleset 11104075, or a job that
the `Run Python Tests` aggregate (`pytest.yml:test-result`) requires. This
session did not read the live ruleset. The pin is checked against it twice a
week by `ruleset-context-drift.yml`.

These kinds are a measurement aid, not a placement rule. ADR-104
(`.project-toolkit/architecture/ADR-104-gate-tier-placement-and-budgets.md`)
still decides placement, in particular rule 4 (a local check must not be a
more expensive copy of a required CI check) and rule 5 (a check over its
tier's target is replaced by a cheaper one). For a CI-owned job, the local run
is early feedback, and it is the only kind of job slice 4 could move without
first building a CI twin. Whether it should move is a rule 4 cost comparison
this record does not make. For every other kind,
removing the local run removes the enforcement.

## Counts

| Hook | Jobs | Unscoped | guard | writer | CI-owned | local only | advisory |
|---|---|---|---|---|---|---|---|
| pre-commit | 47 | 6 | 5 | 12 | 3 | 22 | 5 |
| pre-push | 27 | 17 | 6 | 0 | 1 | 15 | 5 |

"Unscoped" means no `glob`, no `{staged_files}` or `{push_files}`, and no
`use_stdin`. The four CI-owned jobs are `python-format`, `workflow-validation`,
`context-output-check`, and `zero-collection-tests`. `python-tests` is local
only by the same rule: CI runs the full suite, which covers more, but the
hook runs a testmon selection, so the modes differ.

## Checks retained at more than one boundary

| Check | Where it runs | Why | Measured cost of the repeat |
|---|---|---|---|
| `repo-health`, `repair-packed-refs` | pre-commit and pre-push | Guards on shared local state that can break between a commit and a push (#4698). Retained. | 0.1s each |
| `branch-context-policy` | pre-commit and pre-push | Same subcommand at both. No reason for the second run is recorded. Candidate for slice 3. | 0.3s to 0.5s |
| Legacy `.agents` write-target scan | pre-commit `agents-write-targets`, then `pre_pr.py` gate at push, then a non-required CI job | No reason for the push-time repeat is recorded. Candidate for slice 3. | 27.8s at commit, 24.8s again at push |
| Subprocess-encoding scan | pre-commit `subprocess-encoding`, then `count-ratchets` registry entry, then `pre_pr.py` gate | Commit rejects a new offender, the ratchet bounds the count, and the `pre_pr.py` gate repeats the scan. The third run is the candidate. | 15.3s at commit, 15.1s again at push |
| Review-axis drift, security suppressions, placeholder identity, mypy, workflow local run | a pre-push job and again as a `pre_pr.py` gate in the same push | `pre_pr_sequence.py` defers five gates through `already_run_by`. These five are not deferred, so each runs twice per push. Candidate for slice 3. | not separated in this capture |
| Staged dash ban | pre-commit `staged-dash-policy`, then pre-push `dash-prohibition` | Pre-push covers the whole range, including commits made without the hook. Retained. | under 1.1s |
| Suppression comments | pre-commit, pre-merge-commit, pre-push, and required CI (`Run Python Tests`) | Security check. CI equivalence is unproven, so the local copies stay. Retained. | under 1s each |

## Gaps this table exposes

- **semgrep runs only locally.** `security-scan` is the only semgrep run.
  CodeQL, the required CI scanner, is a different tool, so a push made without
  hooks gets no semgrep scan.
- **actionlint can run nowhere.** Pre-commit `actionlint` skips when the binary
  is absent, `pre_pr.py` licenses `Workflow YAML Validation` as `BLOCKED` when
  it is absent (`evidence.py` `default_pre_pr_policy`), and `pr-validation.yml`
  keeps actionlint out of CI on purpose. On a host without actionlint, which
  includes this container, no boundary runs it.
- **37 jobs are local only, and 20 of those have no CI twin at all.** A
  contributor who commits without hooks skips them. That is the existing
  design, and this record does not change it. It is why slice 4 needs a proven
  CI twin before it moves anything.

## The table

Warm p50 is per change class (markdown, python, workflows) from the latency
record. A dash means the job did not run in that class, because its glob did
not match. Kinds and owners follow the rules above.

### pre-commit (47 jobs)

| Job | Scope | Warm p50 md / py / wf (s) | Kind | Owner | CI counterpart | Why |
|---|---|---|---|---|---|---|
| `repo-health` | unscoped | 0.1 / 0.1 / 0.1 | guard | pre-commit | none | Probes the shared `.git/config` (#4698); CI never sees local state. |
| `repair-packed-refs` | unscoped | 0.1 / 0.1 / 0.1 | guard | pre-commit | none | Repairs the local `packed-refs` file; CI never sees local state. |
| `branch-policy` | unscoped | 0.3 / 0.3 / 0.3 | guard | pre-commit | none | Refuses a commit to a protected branch at the moment of the commit. |
| `branch-context-policy` | unscoped | 0.3 / 0.3 / 0.3 | guard | pre-commit | none | Reads the local branch and session state; fails open on ambiguous input. |
| `push-lock-commit-guard` | unscoped | 0.1 / 0.1 / 0.1 | guard | pre-commit | none | Refuses a commit while this checkout holds the push lock (#5123). |
| `markdown-autofix` | glob, staged_files | 1.9 / - / - | writer | pre-commit | none | Rewrites staged markdown; only a commit-time hook can stage the fix. |
| `markdown-check` | glob, staged_files | 1.9 / - / - | local only | pre-commit | none in CI; `pre_pr` gate Markdown Linting runs locally only | No workflow lints markdown. |
| `root-hygiene-policy` | staged_files | 0.5 / 0.7 / 0.7 | local only | pre-commit | none | No CI twin. |
| `session-policy` | glob, staged_files | - / - / - | local only | pre-commit | none | No CI twin. |
| `staged-dash-policy` | glob, staged_files | 0.5 / 0.8 / - | local only | pre-commit | none | No workflow checks dashes; pre-push `dash-prohibition` covers the branch range. |
| `action-pin-policy` | glob, staged_files | - / - / 0.8 | local only | pre-commit | `sha_pinning.py --ci` in Validate Generated Files (required; different script) | Equivalence to the staged check is unproven. |
| `root-scratch-policy` | staged_files | 0.5 / 0.7 / 0.8 | local only | pre-commit | none | No CI twin. |
| `conflict-marker-policy` | staged_files | 0.5 / 0.7 / 0.8 | local only | pre-commit | `tracked-conflict-markers` in Validate PR (required; different subcommand) | Whole-tree CI check is a likely superset; same pattern set unproven. |
| `python-autofix` | glob, staged_files | - / 0.7 / - | writer | pre-commit | ruff ratchet in Run Python Tests (different script) | Rewrites staged Python; only a commit-time hook can stage the fix. |
| `python-check` | glob, staged_files | - / 0.5 / - | advisory | pre-commit | ruff ratchet in Run Python Tests (different script) | Findings exit 0; tool errors block. |
| `python-format` | glob, staged_files | 0.1 / 0.2 / - | CI-owned | required CI | `ruff format --check .` in Run Python Tests (required; primary leg, whole tree) | Same tool and mode on a superset of the files. |
| `workflow-validation` | glob, staged_files | - / - / 0.7 | CI-owned | required CI | `validate_workflows.py` in Validate PR (required; whole tree, no path filter) | Same script on a superset of the files. |
| `actionlint` | glob, staged_files | - / - / - | local only | pre-commit | none (pr-validation.yml keeps actionlint out of CI on purpose) | Skips when the binary is absent, so a skip reads as a pass. |
| `yaml-advisory` | glob, staged_files | - / - / 0.8 | advisory | pre-commit | yaml-lint.yml (not required) | Always exits 0. |
| `skillforge` | glob, staged_files | - / - / - | local only | pre-commit | none | No CI twin. |
| `skill-size` | glob | - / - / - | local only | pre-commit | none | No CI twin. |
| `colocated-skill-tests` | glob | - / - / - | local only | pre-commit | none | No CI twin. |
| `agents-write-targets` | glob | 27.8 / 27.7 / 27.8 | local only | pre-commit | validate-vendor-portability.yml (not required) | CI twin is not a required check. Scans the whole index on any matching commit. |
| `planning-advisory` | glob | - / - / - | advisory | pre-commit | validate-planning-artifacts.yml (not required; different script) | Findings are advisory. |
| `infrastructure-advisory` | glob, staged_files | 0.2 / 0.4 / 0.4 | advisory | pre-commit | none | Exit 0 without `--require-security-review`. |
| `adr-review-policy` | glob, staged_files | - / - / - | local only | pre-commit | none | No CI twin. |
| `taste-advisory` | glob, staged_files | 0.6 / 0.9 / 0.8 | advisory | pre-commit | taste error-count ratchet in Validate PR (different script) | Findings exit 0; script errors block. |
| `security-suppressions-staged` | glob | - / 0.8 / 0.7 | local only | pre-commit | `security-suppressions-diff` in Run Python Tests (required; different subcommand) | Security check; equivalence unproven, so it stays local. |
| `subprocess-encoding` | glob | - / 15.3 / - | local only | pre-commit | subprocess-encoding count ratchet in count-ratchet guard (required; count, not per file) | A count ratchet does not reject a single new offender the way this does. |
| `generate-mcp-config` | glob | - / - / - | writer | pre-commit | none | Regenerates MCP config into the commit. |
| `stage-mcp-config` | glob | - / - / - | writer | pre-commit | none | Stages the regenerated MCP config. |
| `generate-agents` | glob | - / - / - | writer | pre-commit | `build_all.py --check` in Validate Generated Files (required) | Regenerates into the commit; CI only detects staleness. |
| `generate-agent-catalog` | glob | - / - / - | writer | pre-commit | `build_all.py --check` in Validate Generated Files (required) | Regenerates into the commit; CI only detects staleness. |
| `stage-generated-agents` | glob | - / - / - | writer | pre-commit | none | Stages the regenerated agents. |
| `memory-token-update` | glob | - / - / - | writer | pre-commit | none | Rewrites memory token counts into the commit. |
| `stage-memory-index` | glob | - / - / - | writer | pre-commit | none | Stages the rewritten memory index. |
| `memory-size` | glob | - / - / - | local only | pre-commit | none | No CI twin. |
| `memory-index` | glob | - / - / - | local only | pre-commit | none | No CI twin. |
| `memory-token-counts` | glob | - / - / - | local only | pre-commit | memory-index token ratchet in Validate PR (different script) | Equivalence unproven. |
| `memory-tier` | glob | - / - / - | local only | pre-commit | none | No CI twin. |
| `memory-cross-reference` | glob, staged_files | - / - / - | writer | pre-commit | none | Rewrites cross-references into the commit. |
| `stage-memory-cross-references` | glob | - / - / - | writer | pre-commit | none | Stages the rewritten cross-references. |
| `memory-placement` | glob, staged_files | - / - / - | local only | pre-commit | `check_memory_placement.py --ci --changed-since` in Validate PR (required; different mode) | Local runs `--staged`, CI runs `--changed-since`; equivalence of the two modes unproven. |
| `memory-skill-format` | glob | - / - / - | local only | pre-commit | none | No CI twin. |
| `extract-session-episodes` | glob, staged_files | - / - / - | writer | pre-commit | none | Writes episode files into the commit; per-file failures are advisory. |
| `context-output-check` | unscoped | 1.3 / 1.3 / 1.3 | CI-owned | required CI | context-output guard in Run Python Tests (required; same script and manifest) | Same script and manifest; also runs at pre-merge-commit (#5836). |
| `github-bash-policy` | glob, staged_files | - / - / - | local only | pre-commit | none | No CI twin. |

### pre-push (27 jobs)

| Job | Scope | Warm p50 md / py / wf (s) | Kind | Owner | CI counterpart | Why |
|---|---|---|---|---|---|---|
| `repo-health` | unscoped | 0.1 / 0.1 / 0.1 | guard | pre-push | none | Probes the shared `.git/config` (#4698); CI never sees local state. |
| `repair-packed-refs` | unscoped | 0.1 / 0.1 / 0.1 | guard | pre-push | none | Repairs the local `packed-refs` file; CI never sees local state. |
| `mutation-safety` | unscoped | 0.1 / 0.1 / 0.1 | guard | pre-push | none | Reads a local machine-state marker. |
| `push-ref-staleness` | stdin | 0.6 / 0.6 / 0.6 | guard | pre-push | none | Needs the pushed ref payload; CI has none. |
| `push-ref-policy` | stdin | 0.9 / 1.0 / 1.1 | guard | pre-push | none | Security: protected branch, non-fast-forward, shallow clone, and review-marker checks on the pushed refs. |
| `security-suppression-policy` | stdin | 0.3 / 0.3 / 0.3 | local only | pre-push | `security-suppressions-diff` in Run Python Tests (required) | Security check over the push range; also re-run inside `pre-pr-validation`. |
| `placeholder-identity` | stdin | 0.4 / 0.4 / 0.4 | local only | pre-push | placeholder-identity-check.yml (not required) | CI twin is not required; also re-run inside `pre-pr-validation`. |
| `count-ratchets` | unscoped | 72.5 / 71.1 / 75.0 | local only | pre-push | split across count-ratchet guard and Validate PR (both required) | The union equals the registry only by inference; unproven. |
| `python-unreachable-statements` | unscoped | 42.0 / 42.0 / 44.4 | local only | pre-push | none | No CI twin. |
| `path-normalization` | unscoped | 15.0 / 14.8 / 15.2 | local only | pre-push | Validate Path Normalization (required, but behind a path filter) | Whole-tree check behind a diff path filter, so CI can skip it. |
| `planning-artifacts` | unscoped | 0.2 / 0.2 / 0.2 | local only | pre-push | validate-planning-artifacts.yml (not required) | CI twin is not required. |
| `branch-context-policy` | unscoped | 0.4 / 0.4 / 0.5 | guard | pre-push | none | Reads the local branch and session state; fails open on ambiguous input. |
| `review-axis-drift` | unscoped | 0.3 / 0.3 / 0.3 | local only | pre-push | drift check in Validate Generated Files (required; different entry point) | Also re-run inside `pre-pr-validation`. |
| `dash-prohibition` | unscoped | 0.8 / 0.8 / 0.8 | local only | pre-push | none | No workflow checks dashes. |
| `security-scan` | stdin | 0.6 / 21.2 / 31.2 | local only | pre-push | none (CodeQL is a different scanner) | Security: semgrep has no CI twin, so this is the only semgrep run. |
| `pre-pr-validation` | unscoped | 251.6 / 231.5 / 241.0 | local only | pre-push | none (no workflow runs `pre_pr.py`) | Aggregate of 115 gates, run in sequence; on a push, 5 defer to the pre-push job that already ran them. |
| `worktree-gc-report` | unscoped | 1.1 / 1.2 / 1.3 | advisory | pre-push | none | Reports local worktree state; never blocks. |
| `branch-config-prune-report` | unscoped | 0.5 / 0.6 / 0.6 | advisory | pre-push | none | Reports local branch config; never blocks. |
| `python-tests` | unscoped | 30.3 / 15.2 / 15.3 | local only | pre-push | pytest partitions in Run Python Tests (required; full suite, different mode) | The hook runs a testmon selection and CI the full suite, so the modes differ; CI covers more, but equivalence by this table's rule is unproven. |
| `zero-collection-tests` | unscoped | 42.4 / 42.6 / 44.0 | CI-owned | required CI | zero-collection guard in Run Python Tests (required; same script) | Same script, no path filter. |
| `python-lint-advisory` | glob, push_files | - / 0.4 / - | advisory | pre-push | ruff ratchet in Run Python Tests (different script) | Findings exit 0; tool errors block. |
| `python-type-check` | glob, push_files | - / 0.8 / - | local only | pre-push | mypy ratchet in Run Python Tests (required; different script) | Also re-run inside `pre-pr-validation`; equivalence unproven. |
| `workflow-local-run` | glob, push_files | - / - / 0.7 | local only | pre-push | none | Needs `act`; also re-run inside `pre-pr-validation`. |
| `additions-advisory` | unscoped | 0.5 / 0.6 / 0.6 | advisory | pre-push | none | Advisory by design. |
| `hook-anchoring-e2e` | glob, stdin | - / - / - | local only | pre-push | plugin-cli-smoke.yml (not required) | CI twin is not required. |
| `plugin-load-e2e` | glob, stdin | - / - / - | local only | pre-push | plugin-cli-smoke.yml (not required) | CI twin is not required. |
| `bot-cascade-advisory` | unscoped | 0.8 / 1.0 / 0.9 | advisory | pre-push | none | Advisory by design; needs `gh` and an open PR. |

