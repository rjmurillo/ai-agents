# ADR Debate Log: ADR-109 amendment, PR-quality prompt subset retired

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-109-debate-log-3.md` (closed)
- **Outcome**: Consensus
- **Final Status**: accepted

The change adds "Amendment 2026-11-19: the PR-quality prompt subset is retired".
It replaces two citations of the deleted prompt generator with a pointer to that amendment.
The ADR lifecycle gate (`cited-paths-exist`) fails on a citation to a deleted file.
The edit is prose and records a retirement the same change makes, so the reduced panel ran.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Disagree-and-Commit |

### Key Issues Addressed

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | "only user-facing surfaces" was too broad: rules, hooks, and workflow inputs exist. | P2 | Now "the only user-invoked prompt surfaces". |
| 2 | "no workflow changed" was ambiguous: one workflow lost its drift step. | P2 | Scoped to workflows that read the input files, and the drift-step removal is named. |
| 3 | Decision text and the B3 row still describe the `prompts` row as planned. | P3 | Kept, following the earlier amendment pattern; both now point to the amendment. |
| 4 | Two tests use deleted prompt paths as glob-match strings. | P3 | Recorded as stale fixtures; they read no file. |

### Claims Checked

| Claim | Result |
|---|---|
| Generator, drift wrapper, 12 gate copies, and 9 user-invoked prompts deleted | VERIFIED |
| `binplace.yaml` has no `prompts` row; no `review-axis-drift` job; no drift step | VERIFIED |
| `pr-quality` reads the review references | VERIFIED |
| Workflow input files remain | VERIFIED |
| Nothing else read the twelve copies | VERIFIED for live code |
