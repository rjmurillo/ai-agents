# Skill preamble tiers: measured cost, no measured benefit

Date: 2026-11-26. Tree: `feat/always-on-micro-core` at a03ac30444 (2026-11-26).
Record it answers: `.project-toolkit/architecture/ADR-129-always-on-core-rule-admitted-by-eval.md`,
section "Direction, Not Decided: Skill Preamble Tiers".

## Finding

A tiered preamble adds 7,348 to 9,679 bytes to each skill that takes one.
No eval in this repo shows that the added text changes what an agent does.
None of the nine partials in the tiers has passed the test ADR-129 set for always-on text.

So the tiers should not ship on the argument that another project uses them.
They should ship only for the partials an eval admits.

This is the convention this repo was about to copy, and a concrete reason it does not fit here.
The reason is the admission rule the repo already wrote down. A preamble is always-on text for the
skills that take it. It deserves the same gate.

## What this finding does not say

- It does not say skill-delivered rule text is inert. The opposite is measured. See "Evidence" item 2.
- It does not say the nine partials have no effect. No run measured them. Benefit is unmeasured, not absent.
- It does not say the existing includes in `plan` and `build` should go. No run measured their removal.

## Evidence

Three states, kept apart.

| Claim | State | Source |
|---|---|---|
| Cost of the tier text | VERIFIED | Pilot build on this tree, 2026-11-26 |
| Benefit of the tier text, direct | NOT RUN | No tier eval exists |
| Benefit of the tier text, indirect | Weak null | ADR-129 Decision 2; six runs reject only at 6 of 6 |

### 1. Cost, measured

A pilot built two composites from the grammar ADR-129 describes. It was not committed.

| Partial | Rendered bytes | Tier |
|---|---|---|
| `writing-style` | 1,985 | 2 |
| `voice-banned-vocabulary` | 523 | 2 |
| `completeness-scores` | 1,761 | 2 |
| `confusion-protocol` | 2,590 | 2 |
| `clear-the-gate` | 266 | 2 |
| `own-and-flag` | 223 | 2 |
| `search-before-building` | 814 | 3 |
| `boil-the-lake` | 796 | 3 |
| `user-sovereignty-detail` | 721 | 3 |

Tier 2 renders 7,348 bytes. Tier 3 renders 9,679 bytes.

| Pilot skill | Tier | Bytes before | Bytes after | Result |
|---|---|---|---|---|
| `build` | 2 | 21,475 | 28,829 | Fails `skill_size.py --ci`: ceiling 24,576 |
| `plan` | 3 | 18,192 | 21,541 | Passes. It already carried three of the partials |

A draft tier list put 56 templates in tier 1, 39 in tier 2 and 26 in tier 3 at a03ac30444 (2026-11-26).
One agent wrote that list by role. Nobody reviewed it.

On that list, 20 of 65 tiered skills cross the 24,576-byte skill ceiling at a03ac30444 (2026-11-26).
A lean variant keeps only `voice-banned-vocabulary`, `clear-the-gate` and `own-and-flag` in tier 2.
It renders 1,012 and 3,343 bytes. Five skills still cross the ceiling:
`pr-comment-responder`, `pr-review`, `push-pr`, `review` and `ship`.

ADR-129 cuts 17,178 always-on bytes per session.
One tier 3 skill load returns up to 9,679 of them. Two loads can return more than the cut.
How often a session loads a tiered skill is not measured, so the net is not known.

### 2. The transport works

`evals/reports/rule-activation-always-on-core-2026-11-26.md`, section "Results: the core in a skill body".

| Model | Positive pool, skill body minus bare request | p | HEAD rule minus no rule |
|---|---|---|---|
| claude-sonnet-5-5 | +1.05 | 0.002 | +1.17 |
| claude-opus-5-5 | +0.83 | 0.001 | +1.06 |

A skill body lifts scores about as much as an always-on rule does.
That run put the `core` text in the skill body, not the tier partials.
So the delivery path is sound. The open question is which text earns a place on it.

### 3. No scenario exercises the tier text

Scenario files read: `tests/evals/rule-scenarios/voice.json` (17 scenarios) and `builder-ethos.json` (9) at a03ac30444 (2026-11-26).

| Partial | Scenario that exercises it | Does `core` already carry it |
|---|---|---|
| `writing-style` | None | Partly. Clause 7 says point first and name files, lines, numbers |
| `voice-banned-vocabulary` | None | No |
| `completeness-scores` | None | No |
| `confusion-protocol` | None | No |
| `clear-the-gate` | V7 to V12 test evidence states | Mostly. Clause 1 states them; `core.json` reruns V7, V9, V11 and V12 |
| `own-and-flag` | None | No |
| `search-before-building` | None | No |
| `boil-the-lake` | None | No |
| `user-sovereignty-detail` | V3 and R8 test a user override | The override, yes, in clause 5. The two-model case, no |

Seven partials have no scenario at all. Two overlap scenarios that `core` already answers.
Zero of nine have a scenario that tests text `core` lacks.

### 4. The indirect evidence is a weak null

ADR-129 Decision 2 removed `voice` and `builder-ethos` from the always-on set.
The gate did not reject that cut. Mean margins were +0.03 and -0.02 for `voice`,
and +0.04 and +0.17 for `builder-ethos`. Sign counts were 5 to 1 and 4 to 2.
Six runs can reject a cut only at 6 of 6, so this is a null with low power.
It covers only the scenarios that exist. It cannot speak for the seven partials with none.

## Why the convention does not transfer

ADR-129 took the tier shape from gstack. gstack injects a preamble into every skill that needs it,
because the entry point is unknown. That reason holds for text with no always-on home.

This repo has an always-on home. `core` loads on every path, and an eval gate governs what stays in it.
The text an eval could show to matter is already there.
What is left for a preamble is the text no eval has shown to matter.

gstack's own evidence for its tiers was not reviewed for this note.

## What follows

1. Do not ship composite tiers by role.
2. Treat a partial as always-on text for the skills that include it. Admit it the way ADR-129 admits a clause.
3. Write a scenario before a partial spreads. Seven partials need one. Issue #7502 tracks the gap.
4. Keep explicit single includes where a skill's own job needs the text. `plan` and `build` do this today.
5. ADR-129's Direction section still names the gstack model as the intended path.
   That section binds nothing. The owner decides whether a later record replaces it.

## The test that would reverse this

Run a skill-routed eval with two arms on the same skill: with the tier composite and without.
Use scenarios that exercise the partial text, written before the scores are read.
Admit a partial that passes the ADR-129 gate lines. This test is NOT RUN.

## Limits

- The pilot measured bytes, never behavior.
- The tier list is one agent's draft. The count of 20 skills depends on it.
- Byte counts are for the Claude tree. Other host trees were not measured.
- Load frequency per session is unknown, so no net token figure is claimed.
- The pilot files are not in the tree. This note records their sizes.
