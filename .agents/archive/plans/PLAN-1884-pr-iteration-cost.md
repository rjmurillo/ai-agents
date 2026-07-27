---
type: plan
id: PLAN-1884
title: PR iteration cost reduction, pre-push validation hooks
status: active
priority: P1
related:
  - REQ-015
  - DESIGN-015
  - TASK-015
  - issue: 1884
  - issue: 1885
author: milestone-planner
created: 2026-05-04
updated: 2026-05-04
---

# PLAN-1884: PR iteration cost reduction, pre-push validation hooks

## Overview

Four milestones deliver three Claude Code PreToolUse hooks that block `git push` when markdown style violations, marketplace count drift, or session log placeholder values are present. M1 delivers the shared `push_guard_base.py` framework. M2, M3, M4 each deliver one hook. M2, M3, M4 ship sequentially in that order to avoid `hooks.json` merge conflicts (see Risk R-A). The plan is anchored to REQ-015, DESIGN-015, TASK-015; this document adds exit criteria, PR ergonomics, risk mitigations, and the revisions that the critic and pre-mortem flagged.

## Objectives

- Reduce mechanical-error review iterations by at least 50% against the 14-day RCA window (REQ-015 success metric).
- All four milestones merged within a single sprint cycle.
- Zero regressions to existing `Bash(git push*)` hooks (branch context, branch protection, retrospective gate).

---

## Dependency Graph

```
M1 (push_guard_base.py)
    |
    +--> M2 (markdownlint guard)
              |
              +--> M3 (manifest count guard)
                        |
                        +--> M4 (session log field guard)
```

M1 is the sole technical prerequisite for M2, M3, M4. The chain M1 -> M2 -> M3 -> M4 is enforced sequentially because all three appended hooks modify `.claude/hooks/hooks.json`, and parallel branches would produce a guaranteed JSON merge conflict on the same `Bash(git push*)` array. Sequencing eliminates the conflict at the cost of total wall-clock time (4 PRs in series, not 1+3 in parallel). Critic flagged this; resolution is sequential.

If parallel implementation is required for time pressure, the documented strategy is: M2 ships first; M3 and M4 each rebase on the merged M2 (and then M3) before pushing. This trades clean parallelism for a managed rebase per branch.

---

## M1: Shared Hook Framework

**Outcome**: `push_guard_base.py` exists, is tested, and is importable by M2, M3, M4. No `hooks.json` change. No user-visible behavior change.

**Exit Criteria**:

- [ ] `.claude/hooks/PreToolUse/push_guard_base.py` created and committed.
- [ ] `tests/hooks/__init__.py` present (create if absent).
- [ ] `tests/hooks/test_push_guard_base.py` created with cases:
  - Consumer-repo skip returns 0.
  - Empty stdin returns 0.
  - Empty `git diff` output returns 0.
  - Unhandled exception returns 0 and prints to stderr.
  - Non-empty violation list returns 2 with `## BLOCKED` header.
  - **AC-11 test**: `Bash(git push*)` matcher cannot be bypassed by `--no-verify` or non-standard syntax. Implement as a unit test that asserts the matcher pattern is `Bash(git push*)` exactly and a static check against `.claude/hooks/hooks.json`.
  - `@{push}..HEAD` fallback to `origin/main...HEAD` when the primary command exits non-zero.
  - Final fallback (when neither command produces output) returns 0 (fail-open) rather than running validators.
- [ ] `pytest tests/hooks/test_push_guard_base.py -v` passes with zero failures.
- [ ] Line coverage on `push_guard_base.py` >= 80% (pytest-cov asserted).
- [ ] `run_guard` callable signature matches DESIGN-015 (accepts `validator_fn`, `globs`, `name`).
- [ ] Bootstrap block is verbatim copy from `invoke_session_log_guard.py` (currently lines 26-49 at HEAD; re-confirm before writing).
- [ ] No modification to `hooks.json`.
- [ ] `python3 scripts/validation/pre_pr.py` runs clean (no BLOCKING issues on this diff).

**Scope (In)**:

- `push_guard_base.py`: lib bootstrap, `skip_if_consumer_repo` call, stdin JSON read, `git diff --name-only @{push}..HEAD` with `origin/main...HEAD` fallback, `run_guard` dispatcher, output formatter, fail-open exception handler.
- Glob matching uses prefix+suffix string checks for patterns like `.claude/skills/*/SKILL.md` (not `fnmatch`, which fails on nested paths). Document the helper inline.
- `tests/hooks/__init__.py` package marker.
- `tests/hooks/test_push_guard_base.py` unit tests including the AC-11 negative-bypass test.

**Scope (Out)**:

- `hooks.json` changes (deferred to M2/M3/M4 each).
- Any of the three validator hooks.
- Integration tests against a real git repo.

**Dependencies**:

- None. M1 has no predecessor.
- `hook_utilities` lib already present at `.claude/lib/hook_utilities/`.

**PR Ergonomics**:

- Branch: `feat/push-guard-base-1884`
- PR title: `feat(hooks): add push_guard_base shared framework for pre-push guards (Refs #1884)`
- Files: 3 (`push_guard_base.py`, `tests/hooks/__init__.py`, `tests/hooks/test_push_guard_base.py`)
- Diff stat shape: ~150-220 lines added, 0 deleted, 0 modified.

**Estimate**: S (2-4 hours) for an implementer familiar with the hook system. M (4-8 hours) for an implementer new to it. Confidence: HIGH for familiar, MED for new.

**Rollback**: Revert the M1 PR. No `hooks.json` entry exists yet; no behavior change on revert.

---

## M2: Markdownlint Guard

**Outcome**: `invoke_markdownlint_guard.py` is live. A `git push` with changed `.md` files containing markdownlint violations is blocked before CI. Machines without `markdownlint-cli2` on PATH are unaffected (fail-open per AC-3).

**Exit Criteria**:

- [ ] `.claude/hooks/PreToolUse/invoke_markdownlint_guard.py` created.
- [ ] `tests/hooks/test_markdownlint_guard.py` created.
- [ ] `hooks.json` modified: markdownlint hook entry appended to the `Bash(git push*)` block after existing entries (`invoke_branch_context_guard.py`, `invoke_branch_protection_guard.py`, `invoke_retrospective_gate.py`). Entry includes `"timeout": 70`.
- [ ] Tests cover:
  - Clean `.md` files pass.
  - Violation blocks with non-zero exit and violation lines on stdout.
  - `markdownlint-cli2` absent: WARN to stderr, returns 0.
  - Empty changeset (no `.md` files): returns 0 without subprocess.
  - **Timeout (revised)**: `subprocess.TimeoutExpired` causes the hook to print a prominent stderr warning, exit 0 (fail-open), so infrastructure latency does not block work. Pre-mortem flagged this; the change reverses DESIGN-015's original "timeout blocks" decision.
  - `OSError` on subprocess invocation (wrong-architecture binary) is caught and treated as fail-open with a stderr warning.
- [ ] `pytest tests/hooks/test_markdownlint_guard.py -v` passes.
- [ ] Line coverage on `invoke_markdownlint_guard.py` >= 80%.
- [ ] `hooks.json` is valid JSON after modification (`python3 -m json.tool .claude/hooks/hooks.json`).
- [ ] Existing `Bash(git push*)` entries are unmodified (verify by diff against M1 HEAD).
- [ ] `python3 scripts/validation/pre_pr.py` clean.

**Scope (In)**:

- `invoke_markdownlint_guard.py`: imports `push_guard_base.run_guard`, defines `_validate_markdown`, handles `shutil.which`, logs binary version to stderr (AC-3a), runs subprocess with `timeout=60`, handles `TimeoutExpired` and `OSError`.
- `tests/hooks/test_markdownlint_guard.py`.
- `hooks.json` append.

**Scope (Out)**:

- Passing `--config` to `markdownlint-cli2` explicitly (config auto-discovered).
- Version pinning beyond AC-3a logging.
- Auto-fix mode.

**Dependencies**: M1 merged.

**PR Ergonomics**:

- Branch: `feat/markdownlint-guard-1884`
- PR title: `feat(hooks): add markdownlint pre-push guard (Refs #1884)`
- Files: 3.

**Estimate**: S (2-4 hours), confidence HIGH. Add 30 minutes for the timeout/OSError fail-open paths.

**Rollback**: Revert M2 PR. `hooks.json` reverts to M1 state.

---

## M3: Manifest Count Guard

**Outcome**: `invoke_manifest_count_guard.py` is live. A `git push` that touches agent templates, skill files, command files, or `.claude-plugin/marketplace.json` is blocked when counts in marketplace description strings disagree with the filesystem.

**Exit Criteria**:

- [ ] `.claude/hooks/PreToolUse/invoke_manifest_count_guard.py` created.
- [ ] `tests/hooks/test_manifest_count_guard.py` created.
- [ ] `hooks.json` modified: manifest count hook entry appended to `Bash(git push*)`. No explicit timeout (default 30s).
- [ ] Tests cover:
  - Counts agree: returns 0.
  - Agent count mismatch: blocks with violation lines plus the `--fix` hint.
  - Skill count mismatch: blocks.
  - Validator config error (return code 2): blocks with parse-error message.
  - Empty changeset (no manifest-affecting files): returns 0 without importing the validator.
  - `repo_root` parameter is passed explicitly to `validate_known_marketplaces`. Pre-mortem flagged that the validator's module-level `REPO_ROOT` is fragile under non-default `sys.path`.
- [ ] `pytest tests/hooks/test_manifest_count_guard.py -v` passes.
- [ ] Line coverage >= 80%.
- [ ] `hooks.json` valid JSON. Existing entries (including M2) unmodified.
- [ ] `docs/SEMANTIC_INDEX.yaml` is NOT in the activation glob list (verified in code review).
- [ ] `python3 scripts/validation/pre_pr.py` clean.

**Scope (In)**:

- `invoke_manifest_count_guard.py`: adds `build/scripts/` to `sys.path`, imports `validate_marketplace_counts.validate_known_marketplaces`, calls it with explicit `repo_root=project_dir`, translates return codes (0 -> allow, 1 -> block with hint, 2 -> block with parse error).
- `tests/hooks/test_manifest_count_guard.py`: mocks the imported function via `unittest.mock.patch`.
- `hooks.json` append.

**Scope (Out)**:

- Modification of `build/scripts/validate_marketplace_counts.py`.
- Extension of `pre_pr.py` (CI already runs the script).
- `docs/SEMANTIC_INDEX.yaml`. It is a semantic search index, not a count manifest, and is
  explicitly NOT in the activation glob list. The hook does not look at it.

**Dependencies**: M1 and M2 merged.

**PR Ergonomics**:

- Branch: `feat/manifest-count-guard-1884`
- PR title: `feat(hooks): add manifest count pre-push guard (Refs #1884)`
- Files: 3.

**Estimate**: S (2-4 hours), confidence MED. Add up to 1 hour if the `sys.path` import smoke check fails.

**Rollback**: Revert M3 PR. No state changes outside the three files.

---

## M4: Session Log Field Guard

**Outcome**: `invoke_session_log_field_guard.py` is live. A `git push` that includes session log files with placeholder values is blocked.

**Exit Criteria**:

- [ ] `.claude/hooks/PreToolUse/invoke_session_log_field_guard.py` created.
- [ ] `tests/hooks/test_session_log_field_guard.py` created.
- [ ] `hooks.json` modified: session log field guard entry appended. Default 30s timeout.
- [ ] Tests cover:
  - All three fields valid: returns 0.
  - `endingCommit: "pending"`: blocks with `<path>:endingCommit pending` violation.
  - `schemaVersion` absent or empty: blocks.
  - `markdownLintRun.Complete: false`: blocks.
  - `markdownLintRun.Evidence` empty string or whitespace-only: blocks.
  - `markdownLintRun.Evidence` placeholder string (`pending`, `TBD`, `n/a`, `none`, `done`, `.`, single-character): blocks. Match is case-insensitive after `strip()`.
  - **Minimum-length check (revised)**: `markdownLintRun.Evidence` shorter than 20 characters is treated as a placeholder. Pre-mortem flagged short-string bypass; minimum length closes that gap.
  - Malformed JSON: blocks with parse-error message.
  - Empty changeset (no `.agents/sessions/*.json`): returns 0.
  - No `.scanned` field check appears anywhere (the real schema has no such field; verified in code review).
- [ ] `pytest tests/hooks/test_session_log_field_guard.py -v` passes.
- [ ] Line coverage >= 80%.
- [ ] `hooks.json` valid JSON. Existing entries (including M2 and M3) unmodified.
- [ ] `python3 scripts/validation/pre_pr.py` clean.

**Scope (In)**:

- `invoke_session_log_field_guard.py`: opens each matching JSON file, checks three fields per AC-6, applies minimum-length and placeholder checks to `Evidence`, produces `<path>:<field> <reason>` violation lines.
- `tests/hooks/test_session_log_field_guard.py`.
- `hooks.json` append.

**Scope (Out)**:

- Semantic verification of `Evidence` against the diff.
- Checking any field beyond the three in AC-6.
- Modifying the existing `invoke_session_log_guard.py` (commit-time guard, separate concern).

**Dependencies**: M1, M2, and M3 merged.

**PR Ergonomics**:

- Branch: `feat/session-log-field-guard-1884`
- PR title: `feat(hooks): add session log field pre-push guard (Refs #1884)`
- Files: 3.

**Estimate**: S (2-4 hours), confidence HIGH.

**Rollback**: Revert M4 PR.

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Trigger |
|----|------|-----------|--------|-----------|---------|
| R-A | Parallel branches collide on `hooks.json` | HIGH | LOW | Enforce sequential delivery M1 -> M2 -> M3 -> M4. If parallel needed, branches rebase on prior merge before pushing. | Two open PRs both modify `Bash(git push*)` array |
| R-B | `markdownlint-cli2` binary version diverges between local and CI | MED | MED | AC-3a logs version to stderr. Compare logs post-rollout; pin if needed. | CI vs local report different violations on same file |
| R-C | `git diff --name-only @{push}..HEAD` returns empty on new branch with no upstream | HIGH | MED | Fallback to `origin/main...HEAD`. If both fail, return 0 fail-open with stderr warning. Test both paths. | Hook exits 0 unexpectedly on a brand-new branch |
| R-D | Force-push reset makes `@{push}..HEAD` empty, hiding violations | MED | MED | Add tests using temporary git repos that reset HEAD; document the residual gap as out-of-scope. | Developer reports a violation slipped through after force-push |
| R-E | `fnmatch` does not handle nested `.claude/skills/*/SKILL.md` paths | MED | LOW | Use prefix+suffix check (`startswith` + `endswith`) instead of `fnmatch` for that glob. Document the helper. | A new nested skill is silently excluded from manifest count |
| R-F | `validate_marketplace_counts.py` `REPO_ROOT` module constant resolves to wrong path under hook import | HIGH | HIGH | Always pass `repo_root=project_dir` explicitly to `validate_known_marketplaces`. Test the parameter is threaded through, not shadowed. | M3 hook imports succeed but validator reads wrong filesystem |
| R-G | Session log `Evidence` placeholder bypass via short or unusual strings | HIGH | MED | Add minimum-length check (>= 20 chars) plus expanded placeholder list (`""`, `"pending"`, `"TBD"`, `"n/a"`, `"none"`, `"done"`, `"."`). Compare after `strip().lower()`. | Agent writes `Evidence: "n/a "` or `"."` and bypasses |
| R-H | Hook timeout under CI runner load | MED | MED | On `TimeoutExpired`, hook fail-opens with stderr warning. Reverses DESIGN-015's original block-on-timeout. | Push blocked with `[TIMEOUT]` line that is infrastructure noise |
| R-I | Subprocess mock leakage between test files | LOW | MED | Use `unittest.mock.patch` per-test, never module-level. Each test isolates its own mocks. | Non-deterministic CI failures across test orderings |
| R-J | Hook ordering: earlier hook in `Bash(git push*)` blocks before new hooks run | HIGH | MED | Documented design: branch-protection-first ordering is intentional. Aggregate-failure dispatcher is deferred. Note in PR descriptions. | Developer fixes branch issue, repushes, sees new violation, repeats |
| R-K | `validate_known_marketplaces` signature changes before M3 | LOW | HIGH | At M3 implementation time, read the function signature and update the hook call accordingly. | M3 hook fails to import with `AttributeError` |
| R-L | Bootstrap block line range shifts in `invoke_session_log_guard.py` | MED | LOW | At M1 implementation time, re-locate the block via `grep`, copy the exact lines. Lines 26-49 at HEAD as of plan creation. | Hook fails to import `hook_utilities` |

---

## Deferred Items

Explicitly NOT in this plan:

- FM-3 (PR description staleness): tracked as #1885. Blocking follow-up, separate spec.
- FM-5 (spec-before-code enforcement): governance change.
- Auto-fix of violations at push time.
- Git pre-push hook bootstrapping for human-authored PRs.
- CI workflow changes.
- Full-repo remediation of pre-existing markdownlint violations.
- Refactor of existing PreToolUse hooks to use `push_guard_base.py`. Deferred until the framework proves stable across M2-M4.
- Integration smoke test against a real temporary git repo (DESIGN-015 mentions as optional M5). Backlog item.
- `markdownlint-cli2` version pinning beyond AC-3a diagnostic logging.
- Aggregate-failure dispatcher that surfaces all hook failures in one push (R-J mitigation candidate).
- Runtime kill switch for individual hooks (per-hook enable/disable flag in `hooks.json`).

---

## Reversibility

Each milestone is reversible by reverting a single PR:

- **M1 revert**: removes `push_guard_base.py` and tests. No `hooks.json` entry exists; no behavior change.
- **M2 revert**: removes `invoke_markdownlint_guard.py`, tests, and the markdownlint entry from `hooks.json`. Reverts to M1 state.
- **M3 revert**: removes `invoke_manifest_count_guard.py`, tests, and the manifest count entry from `hooks.json`.
- **M4 revert**: removes `invoke_session_log_field_guard.py`, tests, and the session log field entry from `hooks.json`.

No database migrations, no shared mutable state changes, no modifications to existing hook files. Reversibility is high; recovery latency is one PR cycle.

There is no runtime kill switch. Disabling a hook requires editing `hooks.json` and committing. If a hook generates 100% false positives post-rollout, recovery is a one-line edit to `hooks.json` (remove the entry) plus a commit.

---

## Open Questions

None. All scope questions resolved during the interview, gap analysis, pre-mortem, and decision-critic review.

---

## Assumptions

- `tests/hooks/` exists or will be created by M1 (`__init__.py`). If it already exists, skip that file.
- `markdownlint-cli2` is installed on developer machines and CI runners. AC-3 covers absence with fail-open.
- `build/scripts/validate_marketplace_counts.py` has no pending uncommitted changes when M3 implements.
- `Bash(git push*)` block in `hooks.json` contains exactly three entries at plan creation: branch_context, branch_protection, retrospective_gate. New entries append after these.
- Bootstrap block remains at lines 26-49 of `invoke_session_log_guard.py` at M1 implementation time. Implementer re-verifies before writing.

---

## Critic Revisions Applied

This plan applies all changes flagged by the plan critic:

1. **`hooks.json` merge conflict**: M2/M3/M4 are sequential, not parallel. R-A is the explicit risk and the mitigation is the sequencing.
2. **AC-11 test assignment**: added to M1 exit criteria (test in `test_push_guard_base.py`).
3. **Estimate confidence**: S (2-4h) for familiar implementers, MED for unfamiliar (M, 4-8h). Noted in each milestone.
4. **Kill switch**: explicitly deferred under "Deferred Items"; recovery is documented in Reversibility.

## Pre-Mortem Mitigations Applied

This plan applies all mitigations from the pre-mortem analysis:

- **Test divergence (1)**: tests use real subprocess invocations where possible (e.g., `python3 -c "..."` as a stand-in binary) and use real session log fixtures.
- **Hook ordering (2)**: documented as R-J. Aggregate-failure dispatcher deferred.
- **`@{push}..HEAD` edge cases (3)**: fallback chain documented in M1 exit criteria; each case is a test fixture.
- **fnmatch limitations (4)**: replaced with prefix+suffix check for nested skill globs.
- **`REPO_ROOT` module constant (5)**: M3 always passes `repo_root=project_dir` explicitly.
- **Session log placeholder bypass (6)**: minimum-length check (>= 20 chars) plus expanded placeholder list.
- **Timeout under CI load (7)**: fail-open on `TimeoutExpired` with prominent stderr warning. Reverses DESIGN-015's original block-on-timeout decision.
