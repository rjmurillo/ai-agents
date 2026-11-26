# ADR-114 Debate Log: Smoke Advisory Retitle (2026-11-26)

## Context

Devin review on PR #7691 found the ADR-114 title stale. It still said "(Except the
Plugin CLI Smoke)", and Decision 5 said the smoke "blocks by design". The
2026-11-05 amendment had already made the smoke advisory.

The edit retitles the record and adds dated notes at each superseded spot. It adds a
short 2026-11-26 amendment that records the notes. It changes no decision, no
workflow, and no list another gate reads, so the reduced panel (architect and
critic) ran under the AGENTS.md trigger. Each seat received the diff, the ADR, and
the claims ledger, not the author's reasoning.

Claims ledger: `.project-toolkit/critique/ADR-114-smoke-advisory-retitle-claims-ledger.md`.

Evidence on 2026-11-26: `advisory_agent_workflows` lists `plugin-cli-smoke.yml` as
entry 7 of 7. The readiness check loader returns those 7 paths. The `main` ruleset
requires 9 contexts, and `CLI Smoke Result` is not one.

## Agent Positions (round 1)

| Agent | Verdict | Findings |
|---|---|---|
| analyst (refuting seat) | Findings | Row 8 read before the edit, so its line list was stale. Rows 2 and 3 not repeatable without a shell or API. ADR-071:628 also says the check blocks merge. |
| architect | Accept | P1: the review diff was stale. P1: amendments say "decision text unchanged", so record the new notes in their own dated amendment. P2: item 3 residual assumes a required check. P2: Decision 5 list count. P2: ledger row 8. |
| critic | Accept | P1: item 6 still describes merge blocking with no note. P2: item 3 residual is moot. P2: line 217 issue scope. P2: cite ADR-071 lines 628 and 640 and flag ADR-071 in the PR body. |

## Resolutions

- Added "Amendment 2026-11-26: retitle and reading notes". It lists every noted spot
  and says no decision changed.
- Moved the line 180 parenthetical out of the 2026-11-05 amendment into the new
  section, so the older amendment keeps its original text.
- Added notes at Decision 13 item 3 (residual moot) and item 6 (the wait holds the
  run, not the merge).
- Decision 5 note now gives the list size with its date.
- Ledger row 8 now says it was read before the edit and lists the after state.
  Row 9 states where lines shift. Row 10 records the exemption code read.
- Ledger cites ADR-071 lines 628 and 640. ADR-071 is flagged in the PR body, not
  edited, because an ADR-071 edit needs its own debate log.
- Not changed: line 217 references issue #6069 as it was scoped. It is history.
- Not changed: the stale review diff was a scratch artifact. Both seats also read the
  live ADR file.

## Outcome

Outcome: Consensus. Both seats returned Accept, and every P1 is resolved above.
Status stays `accepted`. No decision changed.
