# ADR Debate Log: Cross-Harness Permission-Surface Asymmetry

## Summary

- **ADR**: `.agents/architecture/ADR-085-cross-harness-permission-surface-asymmetry.md`
- **Trigger**: PR #3259 replaced the custom Git-hook framework with Lefthook
- **Rounds**: 2
- **Outcome**: Consensus
- **Final Status**: accepted
- **Prior Review**: `.agents/analysis/ADR-085-permission-surface-debate.md`

## Related Work

- Issue #3197 owns the hook reduction program.
- Issue #3217 owns the `skill_first_guard` disposition.
- PR #3259 deletes the custom Git-hook roots and makes `lefthook.yml` the sole
  local Git-hook scheduler.
- ADR-083 protects customer-facing security controls in the shipped plugin.
- ADR-084 sets the consumer-value bar for vendored hooks.
- ADR-086 records the Lefthook migration and treats older custom-hook paths as
  historical evidence only.

## Phase 1 Findings

The six reviewers agreed that active references to the deleted custom Git-hook
framework had to change. Five reviewers also found that replacing the path with
Lefthook or CI implied behavior equivalence that does not exist:

- `skill_first_guard` runs before a raw `gh` command through PreToolUse.
- Lefthook runs on Git events.
- CI runs after repository or pull-request events.
- Neither replacement can observe or prevent an arbitrary raw `gh` command
  before execution.

Reviewers also found stale #3218 survivor accounting, unresolved owner-decision
wording, incomplete ADR-083 security-control inventory, and no canonical debate
artifact under `.agents/critique/`.

## Round 1

### Changes Made

- Added a PR #3259 amendment record.
- Reframed D-A as removal from the vendored surface, not an equivalent
  relocation.
- Required #3217 to identify any observable repository-state invariant, its
  trigger, failure behavior, and acceptance test.
- Required #3217 to record retirement of pre-execution blocking when no approved
  agent-time carrier exists.
- Corrected #3218 retained-consumer accounting and included ADR-083 security
  controls.
- Renamed the resolved decision section to `Owner Decision Record`.
- Corrected trade-offs, consequences, dependent components, and implementation
  notes.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | Structure, traceability, and survivor accounting were corrected. |
| critic | Accept | False carrier equivalence and stale decision wording were removed. |
| independent-thinker | Block | ADR-084 still appeared to require relocation even when no observable invariant existed. |
| security | Accept | The timing loss and required evidence were explicit. |
| analyst | Accept | Claims aligned with ADR-083, ADR-084, ADR-086, and repository state. |
| high-level-advisor | Accept | The amendment stayed within the ratified D-A and D-B decisions. |

## Round 2

### Issue Resolved

Decision 2 now narrows ADR-084 rule 4 for this guard. The requirement to move
internal policy to Lefthook or CI applies only when Git or workflow state exposes
an enforceable invariant. When no such invariant exists, explicit retirement
satisfies the non-vendoring purpose. A post-execution gate that cannot observe or
prevent the original action does not.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |
| independent-thinker | Accept |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Accept |

A final consistency pass after correcting the owner-decision cross-reference and
Alternatives Considered table also returned 6 Accept votes.

## Strategic Review

- **Chesterton's Fence**: passed. ADR-086 records the custom framework's original
  purpose and its Lefthook replacement.
- **Path Dependence**: passed. The amendment prevents reintroducing deleted hook
  infrastructure through stale instructions.
- **Core vs Context**: passed. Lefthook owns commodity scheduling. Repository
  policy remains explicit.
- **Second-System Effect**: passed. The decision forbids a fake post-execution
  replacement for an agent-time guard.

## Outcome

Consensus reached with 6 Accept votes and no open P0 or P1 findings. ADR-085
remains accepted. Issue #3217 must implement and prove the narrowed D-A contract.
