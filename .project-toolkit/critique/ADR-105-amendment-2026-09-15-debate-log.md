# ADR-105 Amendment 2026-09-15: Debate Log

**ADR**: `.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md`
**Amendment**: Decision item 1 records that the bodies of `### Forming the contract` and `### Reactivation` moved from `builder-ethos.md` into the `avoiding-manufactured-work` skill under epic #5456 M4
**Triggering context**: epic #5456 M4 PR4 (branch `refactor/5456-m4-fold-builder-ethos-sections`); code-reviewer finding that ADR-105 item 1 no longer matched the rule file
**Date**: 2026-09-15
**Reviewers**: self-review by the PR author, working from the code-reviewer finding and the owner direction recorded on issue #5456

## Context

ADR-105 item 1 states that section 4 of `builder-ethos.md` owns the Task Completion Contract end to end with five subsections. Epic #5456 M4 directs that always-on rule content fold into the skills that run it, with the always-on rule keeping cross-cutting text only. PR4 moved two subsection bodies out of the rule and left one-sentence pointers under the original headers. Without an amendment the ADR describes a file layout that no longer exists.

## Positions

The code-reviewer (Opus, read-only pass on the PR4 branch) flagged the mismatch as High: the next reader of an accepted ADR gets a contradicted document of record. The owner direction on #5456 (fold always-on content into skills; eval waived for text that survives in a skill) settles the relocation itself, so the only open question was whether to amend item 1 in place or open a superseding ADR.

Self-review position: amend in place. The decision the ADR records (a terminal predicate, a precedence line, four finding classes, one delegated disposition procedure) is unchanged and both quoted texts are byte-identical in the rule file. Only the location of two procedural bodies changed. A superseding ADR for a relocation would record no new decision. `tests/test_completion_terminal_contracts.py` still pins the five headers and the frozen-contract phrase, so the invariant the ADR relies on is enforced, not just described.

## Outcome

**Outcome: Accepted (amendment in place, no status change).** Item 1 gains a dated paragraph naming which bodies moved, where they landed, and that the predicate and precedence line remain the binding always-on text. `status: accepted` and `superseded-by: null` are unchanged.
