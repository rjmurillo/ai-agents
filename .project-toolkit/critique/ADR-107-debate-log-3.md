# ADR Debate Log: ADR-107 citation of superseded ADR-080

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-107-debate-log-2.md`
- **Outcome**: Consensus
- **Final Status**: proposed (the edit changes no ADR status)
- **Scope**: three ADR-080 mentions in ADR-107, found by the issue #7472 research.
- **Panel**: reduced panel, architect and critic. The edit is prose only. No gate, test, or
  validator reads the changed lines.

ADR-080 is `status: superseded`, `superseded-by: ADR-111`. ADR-107 still named ADR-080 as the
record that owns `model:`. Base: `origin/main` at `7dab88e5c`, read 2026-11-20.

## Round 1 Summary

### Key Issues Addressed

- Does ADR-111 now own `model:` on authored artifacts? Yes. Its Decision covers every skill,
  agent, and command (ADR-111 line 97), and its frontmatter carries `supersedes: [ADR-080]`.
- The first draft kept a clause that called ADR-080 the "Source of the evidence, owner, and
  expiry shape". Both seats found that ADR-080 defines only an evidence bar (rule 2) and a
  sidecar manifest (rule 4). It has no owner field, no expiry, and no `review-by`. The word
  "owner" appears in ADR-080 only in its alternatives table, meaning the repo owner.
- The overlay rule in ADR-107 section 7 made the same false claim with "ADR-080-shaped
  evidence".

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit. The ADR-111 bullet is accurate. P1: the kept clause credits ADR-080 with owner and expiry. P2: the section 7 overlay rule has the same misattribution. Leave the issue #2840 history line. |
| critic | Block. Same P1 on the kept clause, and P1 on the section 7 line. P2: "any authored artifact" is broader than ADR-111's skill, agent, and command scope, but that wording predates this edit. No line-number citation depends on the edited region. |

## Round 2 Summary

### Major Changes Made

- Section 7 overlay rule now lists three requirements. Only the measured evidence is credited to
  ADR-080 rule 2, which ADR-111 rule 2 restates. Owner and `review-by` stand on their own. The
  paragraph keeps its line count.
- The ADR-080 bullet now says the record is history and the origin of the measured-evidence bar.
  It says owner and expiry come from ADR-107, not ADR-080.
- The new ADR-111 bullet carries the `model:` ownership.
- The issue #2840 line stays as written. It is a true statement of history.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Both round 1 findings resolved. Optional P2: "behind the adapter exception process" overreaches, since that process never cites ADR-080. Applied: the clause now names only section 7's overlay rule. |
| critic | Accept. Both P1 findings fixed. `check_adr_lifecycle.py` PASS with no violation outside the baseline. Leaving the scope wording P2 as is was reasonable. |

## Decision

Accepted by both seats. The P2 applied after round 2 removes a claim and adds none, so it did
not need a third round. No ADR-107 decision changes. The overlay rule still requires the same
three items.

### Next Steps

None for ADR-107. The three added lines moved a bullet that ADR-109 line 96 quotes. That
citation was already stale on `main`. The owner chose to fix it on this branch, and ADR-109 line
94 followed. See `.project-toolkit/critique/ADR-109-debate-log-4.md`. The "any authored
artifact" scope wording is flagged in the pull request body for the owner, not changed here.
