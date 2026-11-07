# ADR-114 Debate Log: Decision 11 Item 4 Marked Done (2026-11-07)

## Context

The owner deleted the repository secrets `FACTORY_API_KEY` and
`SMOKE_ANTHROPIC_API_KEY` after the 2026-11-06 decision on issue #6143. The edit
moves Decision 11 item 4 from Open to Done, cites fresh API reads, and updates
two lines that called the item open. It changes no workflow, test, or rule that
other gates read, so the reduced panel (architect and critic) ran under the
AGENTS.md trigger. Each seat received the diff and the ADR file, not the author's
reasoning.

## Agent Positions (round 1)

| Agent | Verdict | Findings |
|---|---|---|
| architect | Disagree-and-Commit | P1: Consequences line 128 still said the secrets are a bypass. P1: the 2026-11-06 amendment said "Still open" with no date qualifier. P2: scope the gate claim to the read time. P2: item 4 is long. |
| critic | Disagree-and-Commit | P1: `agent-droid` holds `FACTORY_API_KEY` yet the grep finds no reader, so state the pattern and what that means. P1: "gate binds" needs a cross-reference to item 7 (self-approval). P1: Rollback row omits the deleted secrets. P2: name the environment-secrets reads. P2: deletion time is unrecorded. P2: refresh the environment list. |

## Resolutions

- Consequences line 128 rewritten in past tense, with the closing date.
- Amendment line now reads "Open on 2026-11-06, done 2026-11-07 (see item 4)".
- Item 4 now states the grep patterns and commit. A second grep for `droid`
  under `.github` finds nothing, so no workflow reads the `agent-droid` copy.
- Item 4 says the gate binds "with that state", names the environment-secrets
  and environments reads, and cross-references the item 7 self-approval path.
- Item 4 says the deletion time is not recorded, so the date rests on the read.
- The environments API lists four environments today. `bot-secrets`, `copilot`,
  and `vendor-provenance` return 404 on the secrets read. Item 4 records the
  four-environment list. Item 12's 2026-10-08 list is left as dated history.
- Rollback row says re-creating the two deleted secrets is not needed.
- Item 4 keeps "the gate is spend control, not a trust boundary" (item 10) and
  the `copilot-context-synthesis.yml` stanza-only caveat.

## Dissent

None. Both seats committed after the resolutions.

## Outcome

Outcome: Consensus on the reduced panel. Decision: accept the edit, with every P1
resolved above and P2 items either resolved or recorded.
