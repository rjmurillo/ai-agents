---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14707-b0ca2d7e8-resolve-issue-4897-scope-pr-comment-responder.json
qaCommit: 7cb644c5420617cbbdead5fc6cfe421ed9db1021
---

# Issue 4897 QA Report: Scoped Serena Memory References

## Objective

Validate the branch `fix/issue-4897-scoped-memory-validation` against the two
acceptance criteria in issue #4897:

1. The pr-comment-responder Phase 0 read uses the scoped memory name.
2. A validation check exists that every literal memory reference in skill
   instructions resolves.

## Defect Under Test

`.claude/skills/pr-comment-responder/references/workflow.md` ran a BLOCKING
Phase 0 step:

```python
mcp__serena__read_memory(memory_file_name="pr-comment-responder-skills")
```

No memory resolves under that bare name. The file is tracked at
`.serena/memories/pr-review/pr-comment-responder-skills.md`. Every agent that
followed the instruction literally failed its own blocking gate, and nothing in
the repository could observe the failure.

## Test Results

| Suite | Command | Result |
|-------|---------|--------|
| New gate unit tests | `pytest tests/validation/test_check_skill_memory_references.py` | 32 passed |
| New gate wiring tests | `pytest tests/validation/test_check_skill_memory_references_wiring.py` | 5 passed |
| Registry pin | `pytest tests/validation/test_pre_pr_sequence_registry.py` | 9 passed |
| Stats script | `pytest tests/test_update_reviewer_signal_stats.py` | 52 passed |
| Full validation suite | `pytest tests/validation/ tests/test_update_reviewer_signal_stats.py` | 3090 passed, 1 skipped |
| Pre-PR sequence | `python scripts/validation/pre_pr.py` | 52/52 PASS, exit 0 |
| Lint | `ruff check` on the 5 touched Python files | All checks passed |
| Types | `mypy` on the changed Python files | Success, no issues |

### Mypy ratchet note

The first full `pre_pr.py` run failed the "Mypy Changed Files (ratchet)" gate
with 3 errors. Two were pre-existing `no-any-return` errors in
`pre_pr_sequence.py` that only became visible because registering the new gate
put that file in the changed set; both callbacks returned an untyped validator's
result directly and are now wrapped in `bool()`, matching every other wrapper in
`checks_spec.py`. The third was mine: the wiring test passed a `SimpleNamespace`
where `run_all_validations` declares `argparse.Namespace`. The sibling registry
test escapes this only because it imports the module by bare name, which types
it as `Any`. All three are fixed and the gate passes.

## Gate Evidence

### Full-corpus run (`.claude/rules/ci-scripts.md` MUST 13)

```text
$ python scripts/validation/check_skill_memory_references.py
[PASS] 0 unresolved reference(s) in 57 literal memory read(s) across 941 instruction file(s).
$ echo $?
0
```

### Negative control (the gate fails on the real defect)

Restoring the pre-fix file and re-running:

**Abbreviated summary** (arrow notation condenses the checker's multi-line
output into one line per finding for readability):

```text
$ git checkout origin/main -- .claude/skills/pr-comment-responder/references/workflow.md
$ python scripts/validation/check_skill_memory_references.py; echo $?
[FAIL] 4 unresolved read_memory names in 1 file(s):
  .claude/skills/pr-comment-responder/references/workflow.md:82
    "pr-comment-responder-skills" -- tracked memory with that basename: pr-review/pr-comment-responder-skills
  .claude/skills/pr-comment-responder/references/workflow.md:132
    "cursor-bot-review-patterns" -- tracked memory with that basename: pr-review/cursor-bot-review-patterns
  .claude/skills/pr-comment-responder/references/workflow.md:134
    "copilot-pr-review-patterns" -- tracked memory with that basename: copilot/copilot-pr-review-patterns
  .claude/skills/pr-comment-responder/references/workflow.md:287
    "pr-comment-responder-skills" -- tracked memory with that basename: pr-review/pr-comment-responder-skills
1
```

Each finding names the exact scoped replacement. The file was restored after
the control.

### Mutation sweep (does the test suite actually grade the gate?)

Seven mutants applied to `check_skill_memory_references.py`, each run against
the full test file:

| # | Mutation | Result |
|---|----------|--------|
| 1 | Drop the path-containment guard | KILLED |
| 2 | Drop the symlink guard | KILLED |
| 3 | Drop backslash normalization | KILLED |
| 4 | Include `write_memory` as a reference form | KILLED |
| 5 | Drop the placeholder-name skip | KILLED |
| 6 | Return exit 0 when findings exist | KILLED |
| 7 | Scan only skills, not agents | KILLED |

7/7 killed, 0 survivors. An inverted control (comment-only edit) SURVIVED, which
proves the sweep distinguishes behavior changes from cosmetic ones.

### Wiring control (is the gate actually run?)

Deleting the `_Gate("Skill Memory References", ...)` row from
`pre_pr_sequence._SEQUENCE` fails 4 tests:

```text
FAILED test_check_skill_memory_references_wiring.py::test_the_sequence_runs_the_gate_after_skip_clause_routing
FAILED test_pre_pr_sequence_registry.py::TestRegistryOrder::test_default_run_emits_the_expected_gates_in_order
FAILED test_pre_pr_sequence_registry.py::TestQuickFlag::test_quick_emits_the_same_gates_in_the_same_order
FAILED test_pre_pr_sequence_registry.py::TestSkipTestsFlag::test_skip_tests_does_not_alter_the_gate_list
```

The row was restored and all 46 tests re-verified green.

### Stats-script regression control

`tests/test_update_reviewer_signal_stats.py::test_memory_path` previously
asserted the `MEMORY_PATH` constant against its own literal, so it passed with
the broken path. It now asserts the path resolves to a tracked file. Restoring
the old literal fails it:

```text
assert False
 +  where False = is_file(.serena/memories/pr-comment-responder-skills.md)
```

## Corpus Sweep

No unscoped `pr-comment-responder-skills` reference remains in any instruction
file. The only remaining bare-name occurrences are in the new gate's own
docstrings and test fixtures, where the string is the defect being described or
constructed.

All five scoped names introduced by this branch were verified to exist as
tracked files:

| Name | File |
|------|------|
| `pr-review/pr-comment-responder-skills` | present |
| `pr-review/cursor-bot-review-patterns` | present |
| `copilot/copilot-pr-review-patterns` | present |
| `powershell/powershell-array-handling` | present |
| `github/github-observations` | present |

## Review Axes Run Locally

| Axis | Result |
|------|--------|
| golden-principles | PASS: 29 files scanned, no violations |
| taste-lints | PASS with 2 warnings: 29 files scanned, 0 errors, file-size advisories at 320/500 and 418/500 |
| code-qualities-assessment | WARN (acknowledged, see below) |
| workflow local run (actionlint + act) | actionlint PASS; act skipped, secrets absent locally (exit 4, non-blocking by design) |

The 11 LLM review axes and the Stage-1 spec-compliance gate require Task
subagents that this session could not dispatch, so no SHA-bound `Reviewed-By`
marker was written. The marker is advisory pre-PR and blocking only for `/ship`.

### Acknowledged WARN: code-qualities-assessment cohesion

`assess.py` exits 11 on `check_skill_memory_references.py`: cohesion 5.1 against
a min of 7 for new authored files. The metric is a size-and-definition
approximation, self-labelled "not LCOM" at confidence 0.4. Measured against the
sibling validators it grades the same way:

| File | Cohesion |
|------|----------|
| `check_skill_memory_references.py` (new) | 5.1 |
| `check_skill_skip_clauses.py` | 4.2 |
| `check_rule_activation_coverage.py` | 1.6 |
| `check_vendor_portability.py` | 1.1 |
| `check_skill_md_portability.py` | 1.0 |
| `memory_index.py` | 1.0 |

The new file scores highest in its family. The absolute threshold fires only for
files a change adds, which is why the pre-existing siblings never trip it.
Splitting a 320-line single-purpose gate into modules to satisfy a
0.4-confidence heuristic would break the one-script-per-gate convention every
sibling follows, so the finding is recorded rather than acted on.

### Reverted: the memory decision record

An earlier commit appended 29 lines to
`.serena/memories/pr-review/pr-comment-responder-skills.md` recording the naming
constraint. That file is 690 lines on `origin/main`, 190 over the taste-lints
500-line hard error, so touching it at all pulled a pre-existing `[ERROR]` into
this branch's diff scope:

```text
[ERROR] authored file-size: .serena/memories/pr-review/pr-comment-responder-skills.md:719
  File exceeds 500 lines (719 lines)
```

The append bought nothing an acceptance criterion asked for, and the new gate
enforces the constraint mechanically, which is stronger than a prose note. It
was reverted rather than kept and explained away. Splitting the 690-line memory
is unrelated scope and belongs in its own issue. Post-revert taste-lints: 29
files scanned, 0 errors, 2 size advisories, exit 0.

## Verdict

**PASS**. Both acceptance criteria are met, the gate fails on the real defect
and passes on the fixed tree, the test suite kills every mutant applied to the
gate, and the registration is graded by a control rather than assumed.
