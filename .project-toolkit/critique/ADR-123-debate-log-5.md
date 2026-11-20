# ADR Debate Log: ADR-123 reversibility and ADR-109 prompt-copy readers

## Summary

- **Rounds**: 3 of 10
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

## Round 3 Summary

The `/review` architect axis, round 2, found "guard tests" too vague.
`tests/skills/review/test_codeql_wiring.py:21` read the security copy's content, not its drift.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept (after Block on the first rewrite) |
| critic | Accept (after two Blocks) |

### Key Issues

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | ADR-109:264 did not name the content test that read the copies. | P2 | First rewrite named only `test_codeql_wiring.py`; both seats blocked because `test_context_mode_enforcement.py:103-105` also read the copies. Final text lists both tests and `validate_seed_parity.py`, and drops the exclusive "only" claim. |
| 2 | "Skills and agents are now the only user-invoked prompt surfaces" was false: `metrics-analysis.prompt.md` survives as a workflow input. | P2 | Now says nine of the ten `.prompt.md` files went, and names the tenth and the workflow that reads it. |

## Dissent

None. Every round 3 block was resolved by a text fix, then accepted.
