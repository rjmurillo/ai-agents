# ADR Debate Log: ADR-088 Amendment and ADR-061 Citation Repoint (issue #5951)

## Summary

- **Rounds**: 1
- **Reviewers**: self-review (implementer), no multi-agent debate convened
- **Outcome**: Accepted
- **Final Status**: proposed (ADR-088 status unchanged; this is an amendment, not a new decision)

## Round 1 Summary

### What changed

- ADR-088 gains an "Amendment (issue #5951)" section recording that
  `templates/rules/pragmatic-programmer.md` moved in full into the
  `software-engineering-library` skill as an on-demand reference, and that
  `unified-software-engineering.md`'s Forbidden Patterns blocklist moved
  alongside it, leaving `code-quality.md` and a trimmed
  `unified-software-engineering.md` as the only always-on-on-code-files
  book-derived content. This applies the ADR's own progressive-disclosure
  decision to the two rules its original scope did not cover.
- ADR-061's two `.claude/rules/pragmatic-programmer.md` citations are
  repointed to `.claude/skills/software-engineering-library/references/pragmatic-programmer.md`,
  since the cited file moved and the old path is now a dangling reference
  (canonical-source-mirror.md's citation-freshness discipline).

### Key issues addressed

- Whether the amendment belongs in ADR-088 (extending an accepted
  progressive-disclosure pattern) versus a new ADR: this is a same-shape
  continuation of ADR-088's own decision (issue #3419's instruction-budget
  problem), applied to the two book-derived rules the original scope missed,
  not a new architectural tradeoff. An amendment section is the correct
  weight; a new ADR would duplicate ADR-088's rationale.
- Whether ADR-061's citations should be fixed in the same change: yes,
  because the cited rule file no longer exists at that path once the
  pragmatic-programmer rule is removed, and leaving it would create the
  exact dangling-citation defect canonical-source-mirror.md's "True when you
  wrote it is not true at merge" section warns against.

### Verdict

**Decision: Accepted.** Both edits are documentation-only, reversible
(the moved content is preserved verbatim in the new skill reference, not
deleted), and consistent with ADR-088's already-accepted rationale. No
enforcement behavior, runtime contract, or generator logic changes; the
instruction-budget drop was measured with
`scripts/validation/instruction_budget.py` before committing (95,877 ->
82,569 bytes for `.py`; 94,499 -> 81,191 for `.cs`; 96,491 -> 83,183 for
`.ps1`), clearing ADR-088's acceptance floor of 12,000 bytes.

### Agent Positions

| Reviewer | Position |
|----------|----------|
| implementer (self-review) | Accept: amendment is in-scope for ADR-088, citations are a correctness fix, both are reversible and measured. |

### Next Steps

None. This is a completed, measured documentation change; no follow-up
planning or implementation work is required.

Referenced records: ADR-088, ADR-061.
