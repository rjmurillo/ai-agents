# ADR Debate Log: ADR-069 The Curated Context Corpus IS the Product (Debate 3)

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-069-debate-log-2.md` (closed at round 2, consensus)
- **Outcome**: Consensus
- **Final Status**: accepted

PR #7508 got three bot review findings after debate 2 closed. Two of them needed ADR text edits, so they open this debate.
The edits are prose only and touch no enforcement, so the reduced panel (architect and critic) ran.
Both panelists were fresh agents.
The status and `implemented` values are unchanged. The ADR's Status section still names logs 1 and 2, which hold the acceptance vote. Naming this log there would be another edit after this vote.

### Carried-Forward Issue

Debate 2 closed with no open issue.

## Round 1 Summary

### Key Issues Addressed

- Implementation Notes item 5 said three ADR checks "run on every PR". They run in the pre-PR sequence, which the pre-push hook runs. No workflow calls `pre_pr.py`. The first edit said that and added "No CI workflow runs them".
- The Revisit condition covered "no measurable difference" but not a measurably worse result.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Needs-revision |

The critic found "No CI workflow runs them" too broad. CI pytest runs `check_rule_adr_citations` against the tracked tree in `tests/validation/test_check_rule_adr_citations.py`.

The critic's reservation was that the research-frontier template named only the "no difference" outcome, so the template and the ADR now disagreed.

## Round 2 Summary

### Major Changes Made

- Item 5 now ends "No CI workflow calls `scripts/validation/pre_pr.py`", which stays true while CI pytest runs one of the checks.
- The research-frontier template milestone now names both negative outcomes: no measurable difference, or measurably worse.
- The ADR Revisit paragraph restates that definition instead of adding its own claim.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Accept |

### Dissent

None that blocks. The critic noted that the template states its pre-registered controls for the positive result only, not again for the negative one. It called the ADR's "under its pre-registered controls" a fair reading, not a misquote.

### Claims Checked

| Claim | Result |
|---|---|
| The three checks are registered in `scripts/validation/pre_pr_sequence.py` | VERIFIED (lines 407, 424, 430, 2026-11-20) |
| The pre-push job `pre-pr-validation` runs `pre_pr.py --compact` | VERIFIED (`lefthook.yml` pre-push section, 2026-11-20) |
| No `.github/` file calls `pre_pr.py` | VERIFIED (grep, and the comment in `pr-validation.yml`, 2026-11-20) |
| No em or en dashes in the ADR or the template | VERIFIED (both panelists, 2026-11-20) |

## Next Steps

- ADR-107 (Related Decisions) still calls ADR-069 `proposed`. It needs its own debate, and the PR names it as an open follow-up.
