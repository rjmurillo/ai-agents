# ADR Debate Log 3: ADR-057 Criterion 2, Gated Skill Change Exception

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-057-debate-log-2.md`
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted. The record's status is unchanged. This debate covers one sentence.
- **Panel**: reduced, architect and critic. The edit removes a contradiction in prose. It changes no executable enforcement.
- **Trigger**: a review bot on PR #7629 noted that criterion 2 says a behavior change updates scenario expectations alongside the prompt. That contradicts the gated-change freeze.
- **Date**: 2026-11-25

## Exit gates before review

| Gate | Result |
|---|---|
| Claims ledger | NOT RUN. The sentence makes no count, path, or quote claim. Each behavior it names maps to a check function the seats read. |
| Self-consistency | VERIFIED by the architect. Lines 135, 137, 218, and 257 already name the ADR-127 exception. Only line 92 carried the conflict. |

## Round 1 Summary

### Key Issues Addressed

- Criterion 2 told every author to update expectations alongside the prompt. ADR-127 decision 7 items 8 and 10 forbid that for a gated skill change.
- The first draft said only that a kept label may not change. The critic showed that understates the freeze. Adds, drops, and text edits also fail after the first template edit.
- The first draft said "gated change". Without "skill", a reader could apply it to non-gated prompts.

### Major Changes Made

- Line 92 now reads: "An ADR-127 gated skill change is the exception: scenarios, including any dropped through `retired.json`, land before the first template edit and then stay frozen, and a kept scenario's `expected_verdict` may not change (Amendment 2026-11-25)."

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept, with a P2 wording note on `expected_verdict` and `retired.json` |
| critic | Disagree-and-Commit until the full freeze is stated |

## Round 2 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Line 92 matches ADR-127 and the shipped check. |
| critic | Accept. "Gated skill change" scopes it away from non-gated prompts. |

### Next Steps

- None. Richard ratifies the ADR-057 and ADR-127 amendments at merge of PR #7629.
