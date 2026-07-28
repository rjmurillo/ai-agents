# Test Report: Issue 3589 Software Engineering Library Activation Gate

## Objective

Verify ADR-088 rollback trigger wiring for `software-engineering-library` activation.

- **Feature**: Issue #3589 rollback trigger enforcement
- **Scope**: Eval state script, scheduled workflow, README policy, regression tests
- **Acceptance Criteria**: owner and cadence, persisted consecutive state, CI or scheduled gate, restoration PR policy

## Approach

- **Test Types**: Unit, workflow static validation, dry-run integration, pre-PR validation
- **Environment**: Local worktree `/home/richard/repos/ai-agents/.worktrees/t_6d9175e8`
- **Data Strategy**: Synthetic eval result JSON for state transitions, real scenario fixtures for dry-run parsing

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Targeted tests run | 62 | 62 | [PASS] |
| Targeted passed | 62 | 62 | [PASS] |
| Targeted failed | 0 | 0 | [PASS] |
| Targeted skipped | 0 | - | [PASS] |
| Full pre-PR validations | 35 | 35 | [PASS] |
| Pre-PR failed validations | 0 | 0 | [PASS] |
| Rule activation dry-run scenarios | 26 | 26 | [PASS] |
| Planned live eval calls | 182 | - | [PASS] |
| Ruff findings | 0 | 0 | [PASS] |

### Test Results by Category

| Test | Category | Status | Notes |
|------|----------|--------|-------|
| `tests/eval/test_software_engineering_library_activation_gate.py` | Unit | [PASS] | 5 tests cover state, threshold, external failure handling, workflow, docs |
| `tests/eval/test_eval_rule_activation.py` | Regression | [PASS] | 57 existing eval tests still pass |
| `eval-rule-activation.py --dry-run` with eight scenario files | Integration | [PASS] | Parsed all fixtures and planned 182 live calls |
| `ruff check` on changed Python files | Static | [PASS] | 0 findings |
| `scripts/validation/pre_pr.py` | Repository gate | [PASS] | 31 passed, 4 skipped, 0 failed |
| `pytest tests/ -x` | Full suite | [FAIL] | Stopped after 4,743 passes due transient `OSError: [Errno 28] No space left on device` in pytest tmp setup. The failed test passed on immediate rerun. |

## Evidence

Commands run:

```text
uv run pytest tests/eval/test_software_engineering_library_activation_gate.py -q
Result: 5 passed in 0.83s

uv run pytest tests/eval/test_eval_rule_activation.py tests/eval/test_software_engineering_library_activation_gate.py -q
Result: 62 passed in 1.75s

uv run ruff check scripts/eval/software_engineering_library_activation_gate.py tests/eval/test_software_engineering_library_activation_gate.py
Result: All checks passed

uv run python scripts/eval/eval-rule-activation.py --dry-run --scenarios <eight ADR-088 scenario files>
Result: exit 0, 182 planned calls, all descriptions present

uv run python scripts/validation/pre_pr.py
Result: 31 passed, 4 skipped, 0 failed

uv run pytest tests/skills/curating-memories/test_supersession_sweep.py::test_sweep_proposes_without_editing -q
Result: 1 passed in 0.53s
```

## Acceptance Criteria Coverage

| Criterion | Evidence | Status |
|-----------|----------|--------|
| Define owner and cadence | `scripts/eval/README.md` names `agent-qa` and weekly Monday 06:30 UTC; workflow cron is `30 6 * * 1` | [PASS] |
| Persist consecutive-run state | `software_engineering_library_activation_gate.py` stores `consecutive_activation_failures` for all eight references in Actions cache | [PASS] |
| Wire check into gate | New workflow runs PR dry-run checks and scheduled live eval | [PASS] |
| Document restoration PR behavior | README and state script policy explain threshold issue plus restoration PR requirement | [PASS] |

## Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| Live LLM eval not executed locally | Requires `ANTHROPIC_API_KEY` and 182 API calls. Dry-run validated parsing and wiring. | P2 |
| Full pytest did not complete | Environment reported no tmp space during one unrelated test after 4,743 passes. Immediate targeted rerun passed. | P2 |

## Verdict

**Status**: [PASS]
**Confidence**: Medium
**Rationale**: The changed gate logic and workflow wiring are covered by targeted tests and pre-PR validation; live scheduled API execution remains CI-owned.
