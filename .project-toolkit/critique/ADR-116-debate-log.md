# ADR-116 Debate Log

ADR: `.project-toolkit/architecture/ADR-116-unchecked-in-context-rule-violation-failure-mode.md`.
Issue: #5307, finding 5. Date: 2026-10-13.

## Format

Reduced panel: architect and critic. The change proposes a class and edits no executable enforcement and no rule another gate reads. `FAILURE-MODES.md` and `retros.md` are unchanged. The two retros receive appended corrections only.

Each seat ran as a separate read-only `claude -p --model sonnet --permission-mode plan` session. Each received the artifact paths and its seat brief, and no author reasoning. The author fixed findings between rounds. The author did not run a third round on the final text, so the round 2 fixes are checked by the gates below and not by a seat.

## Phase 0: related work

- Issue #5300 asks for this ADR and is open.
- Issue #5288 owned the pre-stage dash check. It is closed by PR #6398, which fixed the shallow-clone half only.
- Issue #5461 is open and also proposes a new FAILURE-MODES class, so the number FM #13 is not reserved.
- Open PR #6437 holds ADR-115. This ADR takes 116.

## Round 1

| Seat | Verdict | Findings |
| --- | --- | --- |
| architect | Disagree-and-Commit | P1 no debate log; P1 no boundary against FM #1; P1 count-based FM #9 boundary; P1 missing "amend FM #1" alternative; P1 severity attribution unsupported; P2 overstated MUST 2 claim; P2 retro-edit wording; P2 08-21 retro unlinked; P2 enforcement is a habit; P2 numbering; P2 thin references |
| critic | Disagree-and-Commit | P1 enforcement repeats the failed habit fix; P1 class defined by outcome; P1 debate requirement misattributed; P1 ADR and retro disagree on 08-21 coverage; P1 class has two names; P2 FM #12 claim overstated; P2 cost and severity partly unsupported; P2 trigger extrapolated |

No P0. Both seats confirmed `retros.md` MUST 2 wording, `lefthook.yml:119`, `pr_description.py:1101`, and the absence of dashes.

Resolution:

- **Fixed.** FM #1 and FM #3 boundary bullets added. Alternatives gained "widen FM #1" and "mechanical pre-stage check". The debate log is this file. The MUST 2 attribution now cites ADR-073 and the retro rule accurately. The 08-21 retro gets its own appended correction. The class has one name. The FM #12 claim and the severity attribution were reworded.
- **Not adopted.** None.

## Round 2

| Seat | Verdict | Findings |
| --- | --- | --- |
| architect | Disagree-and-Commit | P1 no `## Status` section; P1 FM #9 boundary not testable; P1 proportionality conceded but not decided; P2 trigger absorbs any hook rejection; P2 FM #12 cite; P2 `review-by` trigger has no watcher; P2 ADR-073 clause |
| critic | Disagree-and-Commit | P1 evidence contradicts the 08-25 retro's near-miss test; P1 the pre-stage check has no owner; P2 cause stated as fact; P2 FM #12 precedent; P2 FM #13 number hard-coded; P2 "Low" is a new tier; P2 class broader than evidence |

No P0.

Resolution:

- **Fixed.** `## Status` section added with a standalone first sentence. The FM #9 boundary now keys on trigger (unquoted parity claim versus deterministic checker rejection). The class is narrowed to deterministically testable rules, with an exclusion for unpredictable tool output and a boundary line against FM #4 and FM #6. Evidence now says one CI instance and one local catch, and labels the cause INFERRED. A "decline the class" alternative was added. Issue #5288's closed state and the missing check are recorded. Severity is Medium, the lowest index tier. The class number is conditional on acceptance order. The FM #12 sentence cites the index row and ADR-105 only. The "third instance" trigger names the retro as the watcher.
- **Not adopted.** The architect's P1 asks to decide proportionality inside the Decision. The ADR records the weakness as a Negative consequence and a "decline" alternative, and leaves the call to the owner, because the record is `proposed`.

## Outcome

Concluded with Disagree-and-Commit from both seats. Final status: `proposed`. The owner decides acceptance.
