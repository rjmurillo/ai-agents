# ADR Debate Log: ADR-120 The Completion Gate Reports a Refused Session as Unknown (fourth debate)

## Summary

- **Rounds**: 1 of 10. Round 1 reached consensus.
- **Prior debate log**: `.project-toolkit/critique/ADR-120-debate-log-3.md`
- **Claims ledger**: `.project-toolkit/critique/ADR-120-claims-ledger.md`
- **Outcome**: Consensus. Round 1: one Accept, one Disagree-and-commit.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-120-completion-gate-unknown-verdict.md`
- **Edit**: a dated amendment, one Negative bullet, one clause in Decision 4, and two
  References lines. No gate code changes.
- **Trigger**: branch `fix/github-not-found-exit-codes` moves the github skill scripts
  from exit 2 to exit 3 for a missing PR, per ADR-035. The Negative bullet said
  verifier exit 2 means "PR not found", which is no longer true.

Panel: reduced panel (architect, critic), because the edit is prose and changes no
executable enforcement.

## Pre-review gates

| Gate | Result |
|------|--------|
| Claims ledger | VERIFIED, 10 rows |
| Documentation accuracy | VERIFIED by hand against `run_completion_gate.py`, `skill_bootstrap.py`, `not_found.py`, and `get_pr_context.py` |
| Self-consistency | VERIFIED. Decision 4 already scopes the GraphQL probe to exit 2 |
| Refuting seat (haiku analyst) | Three findings, all fixed. See the ledger |

## Round 1 (2026-11-27)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | No Decision item is contradicted; every ambiguous exit still fails safe. |
| critic | Disagree-and-commit | Every factual claim checks out; one dangling reference and one missing caveat. |

### Issues Raised

| # | Seat | Priority | Issue | Resolution |
|---|------|----------|-------|------------|
| 1 | both | P1 | References cite `ADR-120-debate-log-4.md`, which did not exist | Fixed: this file |
| 2 | architect | P1 | "a missing PR there stays `failed`" misstates a shift from `unknown` to `failed` under a GraphQL-only refusal | Fixed: the amendment names the shift |
| 3 | architect | P1 | The Negative bullet "Exit 3 has two meanings" is stale | Declined: that bullet is about the gate's own exit code, which this change does not touch. The verifier meaning sits in the next bullet, which was amended |
| 4 | architect | P1 | Decision 4 lists "a quota or a 5xx" for an exit 3 beside a GraphQL refusal | Fixed: the list now adds "a missing PR" |
| 5 | architect | P2 | Say the gate never reads `Error.Type` | Fixed: one sentence citing Decision 3 |
| 6 | critic | P2 | "never passes" holds only while `fail_open` stays false | Fixed: qualified, citing Decision 1 |
| 7 | architect | P2 | Moving frontmatter `date` erases the decision date | Declined: Amend mode updates `date` as last-updated; the amendment heading keeps the new date and the original date stays in debate log 1 |
| 8 | both | P2 | One amendment line ran past the wrap width | Fixed: rewrapped |

### Claims Checked

| Claim | Agent | Result |
|-------|-------|--------|
| `origin/main` `get_pr_context.py` exited 2 for a missing PR | critic | VERIFIED |
| The branch exits 3 with `Error.Type` `NotFound` | critic | VERIFIED |
| A missing lib exits 2 | critic | VERIFIED |
| `_unanswered_exit` treats any exit above 1 as no answer | critic, architect | VERIFIED |
| REST probe explains 2, 3, 4; GraphQL probe explains 2 | critic, architect | VERIFIED |
| The not-found markers match neither refusal body | critic | VERIFIED |
| Shipped criteria set `fail_open: false` | critic | VERIFIED |

### Carried Forward

None. The live refused-session behavior stays unverified, as the Residual risk section
already says.
