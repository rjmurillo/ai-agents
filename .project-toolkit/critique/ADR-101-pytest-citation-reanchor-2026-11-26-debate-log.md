# ADR Debate Log: re-anchor the ADR-101 pytest citation

## Summary

- **Rounds**: 1 of 10
- **Outcome**: Consensus
- **Final Status**: unchanged
- **Scope**: one line-number citation in `.project-toolkit/architecture/ADR-101-enforcement-planes.md`.
- **Panel**: reduced panel, architect and critic. The edit changes no executable enforcement.
- **Constraint**: the lane brief forbids subagents. The implementer therefore ran the two seats as separate inline review passes and recorded the evidence here.

The edit changes only `pytest.yml:1043-1062` to `pytest.yml:1126-1145`. It changes no decision, status, requirement, or enforcement rule.

## Evidence

The cited sentence claims that `test-result` now runs on `!cancelled()`. In the merged working tree, `.github/workflows/pytest.yml` lines 1126 through 1145 contain the `test-result` job declaration, its required job name, its dependency list, the explanatory comment, and `if: ${{ !cancelled() }}`. The old range no longer contains that job block. The claim is current, while only its location moved.

The validation-lane citation in `tests/validation/test_check_push_lock_before_commit.py` was checked separately. Lines 1292 through 1332 still start at the `test-windows-pwsh` job declaration and end at the `run_pytest_windows.py` command. That range remains correct after the merge.

## Round 1 Summary

### Key Issues Addressed

- Whether a citation-only ADR edit can use the reduced panel. It can, because no executable enforcement or gate-read rule changed.
- Whether the new range supports the sentence. It does, because the range includes both the job and the `!cancelled()` condition.
- Whether neighboring citations need edits. They do not, because the surrounding prose and its other citations are unchanged.
- Whether the merge changed the target again. It did not; the verification ran after merging `origin/main`.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accepted. The edit preserves the architectural record and changes no decision text. |
| critic | Accepted. The new range contains the cited job and condition, and the constraint disclosure is explicit. |

## Decision

Accepted by both seats. Apply the citation re-anchor as a one-line citation correction. No ADR requirement, status, or enforcement behavior changes.
