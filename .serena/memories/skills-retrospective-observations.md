# Skill Sidecar Learnings: Retrospective

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

### Skill-Retrospective-006: Chesterton's Fence Before Infrastructure Change
**Pattern**: When autonomous agents encounter infrastructure patterns (CI runners, labels, permissions), require rationale query before modification. Pattern: "Before changing something, understand why it exists." Session 80 autonomous PR monitoring applied this to: Windows runner (platform-specific tests), label format (repo convention `priority:P1` vs `P1`), permissions (token scope limitations).

**Evidence**: PR #224 ARM migration succeeded after multi-cycle application of Chesterton's Fence principle (merged 2025-12-23). 37.5% cost reduction achieved by understanding constraints before migrating workflows. Label bug (PR #303) detected by questioning why existing format used `P1` instead of `priority:P1`.

**When Applied**: When autonomous agents monitor PRs/workflows and encounter patterns that seem incorrect or inefficient. Query for rationale before proposing changes.

**Anti-Pattern**: Changing configurations because they "look wrong" without root cause analysis, leading to breakage of platform-specific requirements or repository conventions.

**Session**: batch-28, 2026-01-18

---

## Preferences (MED confidence)

None yet.

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.
