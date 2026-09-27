# SPEC: Path-Local Effective Context Measurement

**Issue**: [#4880](https://github.com/rjmurillo/ai-agents/issues/4880)
**Status**: Accepted
**Created**: 2026-09-27
**Baseline commit**: `2628d8c1282277ad39bc605eb6a31131eff2d77e` (the issue's measurement)

## Problem

No command reports which instruction files a harness loads for one target path.
Existing gates measure generated mirrors and three root files only.
Path-local `AGENTS.md` and nested `CLAUDE.md` growth bypasses every budget.

## Step 0 First Principles

### Q1 Demand Reality

The repository owner filed #4880 at P1. Issues #4871 and #4853 name the same gap.
The 2026-08-12 and 2026-08-13 triage comments name it as the blocker.

### Q2 Status Quo

A maintainer runs `wc -c` on candidate files and guesses which ones load.
The issue warns that summing those numbers is wrong.

### Q3 Desperate Specificity

Issue #4880 itself is blocked. It cannot prove a slimming kept behavior.
It cannot stop regrowth, because no gate sees path-local bytes.

### Q4 Narrowest Wedge

A static resolver per harness, a Copilot observe mode, a ratchet test, three fixtures, and one live run.
About 6 hours AI-assisted, about 4 days for a human team.

### Q5 Observation

`.github/AGENTS.md` was 24,932 bytes at the baseline commit and 5,008 bytes at `643e9b4ab`.
PR #5792 made that cut. No gate would catch it growing back.
`copilot instruction list --json` (CLI 1.0.89) lists different local files per working directory.

### Q6 Future-fit

At 10x more directories, the per-target view is the only one that stays honest.
The resolver reads loading rules, not a file list, so new directories need no code change.

## Prior art (Step 0.5)

- `scripts/eval/_runtime_harness.py` records the observed loading rules for both CLIs (2026-09-22, 2026-09-23 probes).
- `scripts/eval/eval_runtime_parity.py` runs real CLIs and resolves instructions from a git ref (`--instructions-ref`).
- Serena memory `instruction-context-efficiency-not-quality` records the rule-membership probe method.
- PR #5792 already slimmed every path-local guide. This spec does not repeat that work.

## Loading model (observed, not inferred)

| Layer | Claude Code | Copilot CLI |
|---|---|---|
| Root | `CLAUDE.md`, its `@` imports, `.claude/CLAUDE.md` | `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` |
| Nested | `CLAUDE.md` in each directory from root to target, with imports | `AGENTS.md` and `CLAUDE.md` in each directory from git root to cwd |
| Scoped | `.claude/rules/*.md` whose `paths:` match the target, or no `paths:` | `.github/instructions/*.instructions.md` whose `applyTo` matches the target |
| User | `~/.claude/CLAUDE.md` (per developer) | `$COPILOT_HOME/copilot-instructions.md` (per developer) |

The user layer is reported but never counted in a ratchet. CI cannot see it.

## Requirements

| ID | Requirement (EARS) | Verification |
|----|-------------|--------------|
| REQ-1 | When a user runs the command with a target path and a harness, the system shall list each loaded file, its layer, and its bytes, plus totals. | Unit tests over a fixture tree |
| REQ-2 | When `--rev` names a commit, the system shall read every file and import at that commit with `git show`. | Unit test against a temporary git repository |
| REQ-3 | When `--observe` is set for Copilot, the system shall run `copilot instruction list --json` in the target directory and fail on any repository file that differs from the static set. | Unit test with a stubbed runner; one live run recorded |
| REQ-4 | If an import cycle, a missing import, or a path outside the repository occurs, then the system shall report it and not follow it. | Negative unit tests |
| REQ-5 | The system shall report the user layer separately and exclude it from totals that the ratchet checks. | Unit test |
| REQ-6 | While the tree is checked, the system shall fail when the path-local bytes for a frozen target and harness exceed its local ceiling. | Ratchet test in `tests/validation/`, run by the required Python test job |
| REQ-7 | The ceilings shall carry a comment that names them local and measured at the accepted state, with no vendor limit attributed. | Test asserts the label text |
| REQ-8 | The analysis shall record before and after inventories for the five frozen targets and both harnesses. | Analysis document |
| REQ-9 | The parity evaluator shall install fixture `path_local` files at their repository paths, resolved from the working tree or `--instructions-ref`. | Unit tests in the evaluator suite |
| REQ-10 | Three frozen fixtures shall exercise SHA pinning, untrusted input in `run:`, and the generated-artifact edit rule under `.github/`. | Dry-run control tests; live before and after runs recorded |

## Frozen targets

| Target | Local layer under test |
|---|---|
| `.github/workflows/pr-validation.yml` | `.github/AGENTS.md`, `.github/CLAUDE.md` |
| `scripts/validation/pre_pr.py` | `scripts/AGENTS.md`, `scripts/CLAUDE.md` |
| `build/scripts/build_all.py` | `build/AGENTS.md`, `build/CLAUDE.md` |
| `templates/agents/analyst.shared.md` | `templates/AGENTS.md`, `templates/CLAUDE.md` |
| `src/claude/agents/analyst.md` | `src/AGENTS.md`, `src/claude/AGENTS.md`, `src/CLAUDE.md` |

## Failure modes

- A harness changes its loading rules. Mitigation: `--observe` compares the static set with the Copilot listing.
- Claude Code has no model-free listing. Mitigation: the live parity fixtures check behavior, not membership.
- A ceiling set too tight blocks honest edits. Mitigation: the ratchet message names the command that shows the new inventory.

## Security

The command reads repository files and runs `git show` and `copilot` as argv lists with no shell.
Paths resolve inside the repository root (CWE-22). No secrets are read or written.

## Observability

The metric is path-local bytes per target and harness, printed by the command and pinned by the ratchet test.

## Out of scope

- Further slimming of path-local files. PR #5792 did it, and the ratchet now holds it.
- Plugin instruction loading. #4871 found no plugin instruction resources on Copilot CLI 1.0.79.
- A second parity harness. This work adds fixtures and one install field to the existing one.

## Deferred

- A Claude membership probe through a live model call. Owner: a follow-up issue if the maintainer wants one.

## CVA summary

Common: every layer is a file, a byte count, and a reason it loaded.
Varies: the discovery rule per harness (imports and `paths:` against ancestors and `applyTo`).
Relationship: one resolver per harness returns the same record type.

## Buy-vs-build decision

Context, not core. Alternatives: `copilot instruction list` (Copilot only, no bytes, no applyTo filter) and the external canary probe from the issue thread (presence only, needs a model call).
Recommendation: build a small resolver, and use the Copilot listing as its check.

## Complexity classification

Tier 3, Complicated domain. Method: analyze, then build with tests first.

## Plan

### Milestones

| ID | Milestone | Exit criteria | Ships alone |
|----|-----------|---------------|-------------|
| M1 | Effective-context command | REQ-1 to REQ-5 tests pass; command runs on the five targets at HEAD and at the baseline | Yes |
| M2 | Path-local ratchet | REQ-6 and REQ-7 tests pass on HEAD; a synthetic growth fixture fails | Yes, after M1 |
| M3 | Path-local parity fixtures | REQ-9 and REQ-10 dry-run controls pass | Yes, parallel with M1 |
| M4 | Evidence | Analysis document holds the REQ-8 inventories, one Copilot observe run, and live before and after fixture runs | After M1 and M3 |

### Tasks

| Task | Milestone | Size | Done when |
|------|-----------|------|-----------|
| T1 | M1 | M | `scripts/validation/effective_context.py` resolves Claude layers (root, imports, nested, rules, user) with tests |
| T2 | M1 | M | Same module resolves Copilot layers (root, nested, `applyTo`, user) with tests |
| T3 | M1 | S | `--rev` reads through `git show`; tests use a temporary repository |
| T4 | M1 | S | `--observe` compares the Copilot listing with the static set; stubbed runner tests |
| T5 | M2 | S | Ratchet constants for five targets by two harnesses; test fails on growth and names the command |
| T6 | M2 | S | Register the check in the pre-PR sequence |
| T7 | M3 | M | Evaluator accepts `path_local`, installs files at repository paths, honors `--instructions-ref`; Copilot listing preflight includes them |
| T8 | M3 | S | Three fixtures with positive and negative controls |
| T9 | M4 | S | Before and after inventories written to the analysis document |
| T10 | M4 | M | Live Claude runs at the baseline and at HEAD; Copilot runs when quota allows; results recorded |

### Dependency graph

T1, T2 then T3, T4 then T5, T6. T7 then T8. T9 needs T3. T10 needs T8.
M1 and M3 run in parallel.

### Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Static model disagrees with the real CLI | Medium | High | T4 observe mode; the analysis records one live listing per target |
| Copilot quota blocks live runs | Medium | Medium | Record the exit code as NOT RUN; Claude runs still prove the Claude path |
| Live fixture pass rate is noisy | Medium | Medium | Three trials per arm; report counts, not one verdict |
| `applyTo` glob semantics differ from Python matching | Low | Medium | Reuse the glob matcher that the instruction budget already uses |
| Ratchet blocks legitimate growth | Low | Low | Failure text names the command and the constant to raise |

### Pre-mortem (run inline)

First failure: the baseline tree lacks a target file. The resolver must use the directory chain, not the file.
Fragile dependency: the evaluator workspace isolation. `path_local` files land inside the workspace only.
Untested assumption: Claude loads a nested `CLAUDE.md` import only after reading a file in that directory. The fixtures make the task read the workflow file first.

### Deferred items

- A Claude membership probe through a live model call.
- Any new slimming edit. None is required by the measured state.
