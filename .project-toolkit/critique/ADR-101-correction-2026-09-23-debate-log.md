# ADR-101 Correction Debate Log (2026-09-23)

## Context

ADR-101 Consequences, Positive, said two of four exhibits were live. One of
them was #4402's `SKIP_SCOPE_CHECK`, which the text said the scope script
"still honours" and lefthook "still runs". Both claims are now false. PR #5723
removed the flag on 2026-09-11. PR #5893 deleted the scope script and its
lefthook jobs on 2026-09-23. Both changes fall under ADR-100.

## Owner Direction

The repository owner chose option A on 2026-09-23: amend ADR-101 with a dated
correction note and leave the Decision untouched. Option B (implement rule 3
generally) was not chosen, because the flag is already gone and rule 3 is
ADR-101's whole unimplemented program. Option C (leave the stale text) was not
chosen, because agents would hunt for a bypass that no longer exists.

## Reviewer Checks

Self-review against the tree on origin/main, commit ced631f3b:

- `git grep SKIP_SCOPE_CHECK -- scripts lefthook.yml .github .claude/lib .claude/hooks`
  prints nothing, so no code path reads the flag.
- The scope script path no longer exists.
- No lefthook job named scope-policy or branch-scope exists.
- The edit touches one bullet in Consequences. The Decision, the rules, and
  the invariant are unchanged. No em or en dashes are added.

## Outcome

Verdict: Accepted by owner direction (option A). The correction is factual, dated, and keeps the four exhibits
as evidence of the class. Only #5177 stays live.
