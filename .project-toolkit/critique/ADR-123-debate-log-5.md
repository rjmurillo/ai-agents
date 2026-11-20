# ADR Debate Log: ADR-123 reversibility and ADR-109 prompt-copy readers

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-123-debate-log-4.md` (closed, consensus)
- **ADRs covered**: ADR-123, ADR-109
- **Outcome**: Consensus
- **Final Status**: unchanged (no ADR status edit)

The `/review` decision-rigor axis found three text defects on 2026-11-20.
ADR-123 Reversibility said the typed declarations are inert without the gate.
The shipped skillforge linter checks the same shape in consumer installs.
ADR-109 said nothing else read the twelve prompt copies.
The edits are prose only, so the reduced panel ran (architect and critic).

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Block |

### Key Issues

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | "No live gate or workflow read" the copies is false. The drift step and the lefthook job read them before this change deleted both. | P1 | Now "Only their own drift guards and guard tests read" the copies. |
| 2 | The ADR-123 Impact row named only the file that registers the rule. The check lives in `_lint_frontmatter_checks.py`, and a shipped doc depends on the shape. | P2 | The row names both scripts, `references/frontmatter-and-limits.md`, and every mirrored harness tree. |
| 3 | The B0 marker looked redundant. | P2 | Kept. The B3 row edit puts B1 within three lines of a change, so the reverse pass checks B1 strictly. |

## Round 2 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Accept |

### Claims Checked

| Claim | Result |
|---|---|
| `lint_skill_frontmatter.py:17,125` registers MUST rule `fm.artifacts.shape` | VERIFIED |
| `artifacts_shape` sits at `_lint_frontmatter_checks.py:181` | VERIFIED |
| `validate_seed_parity.py` reads the copies at a pinned commit, not at HEAD | VERIFIED |
| `_has_ignore_marker` honors a marker on the line above | VERIFIED |
| No decision or status changed | VERIFIED |

## Dissent

None. The critic's round 2 P2 on "drift guards" wording was applied before commit.
