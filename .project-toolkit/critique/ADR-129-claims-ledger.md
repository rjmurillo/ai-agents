# ADR-129 claims ledger

Evidence was read from the working tree of `feat/always-on-micro-core` at d3c2d82df9 (2026-11-26).
Rows 35 to 37, 58, 64, 69 and 74 also cover the ADR-105 `## Amendment 2026-11-26`.
Revision 2 followed panel round 1. The record is now `ADR-129-always-on-core-rule-admitted-by-eval.md`.
Revision 2 added rows 59 to 82. Row 21 backs no claim in revision 2. Row 45 sits after row 48.

| # | Claim | Kind | Command or source | Result |
|---|---|---|---|---|
| 1 | At 8104f11665 the renders were `voice` 12,817, `builder-ethos` 11,244, `universal` 8,879 bytes | count | `git show 8104f11665:src/claude/rules/<rule>.md \| wc -c` | VERIFIED: 12817, 11244, 8879 |
| 2 | Those three sum to 32,940 bytes | count | Sum of row 1 | VERIFIED: 32940 |
| 3 | All three declared `paths: ["**"]` and `priority: critical` at the base | behavior | `git show 8104f11665:templates/rules/{voice,builder-ethos}.md`; `templates/rules/universal.md` lines 2 to 3 | VERIFIED |
| 4 | `core` render is 6,876 bytes | count | `git show HEAD:src/claude/rules/core.md \| wc -c` | VERIFIED: 6876 |
| 5 | `core` declares `paths: ["**"]` and `priority: critical` | behavior | `templates/rules/core.md` lines 2 to 3 | VERIFIED |
| 6 | `core` holds seven clauses and three sections | count | `grep -n '^## \|^[0-9]\. \*\*' templates/rules/core.md` | VERIFIED: clauses 1 to 7; `## Task Completion Contract`, `## Task Intent`, `## Completion-Tail Audit` |
| 7 | Always-on set is 15,762 bytes at d3c2d82df9 | count | 6876 plus `universal` 8886 (`git show HEAD:src/claude/rules/universal.md \| wc -c`) | VERIFIED: 15762 |
| 8 | The cut is 17,178 bytes, 52 percent | count | 32940 minus 15762; 17178 / 32940 | VERIFIED: 17178, 52.1 percent |
| 9 | Gate: -0.20 or better per rule and model; no scenario more than 1.00 below; candidate minus no rule above zero | quote | Eval report lines 31 to 34 | VERIFIED |
| 10 | A registered sign rule exists in `rule-audit-procedure.md` | path | `src/claude/skills/context-optimizer/references/rule-audit-procedure.md` line 209, `#### Registered decision rule, 2026-08-03` | VERIFIED |
| 11 | Seven clauses alone scored -0.87 and -0.78 on the completion tail | count | Eval report lines 260 and 264 | VERIFIED |
| 12 | Seven-clause `universal` scored -0.28 and -0.26 | count | Eval report lines 67 and 73 | VERIFIED |
| 13 | `universal` lost the sign count 6 of 6 | count | Eval report lines 358 and 362 | VERIFIED |
| 14 | `voice` and `builder-ethos` sign counts were 5 to 1 and 4 to 2 | count | Eval report lines 356 to 357 | VERIFIED |
| 15 | `voice` and `builder-ethos` load on `**/SKILL.md`, `**/skills/**/*.mustache`, `**/*.SKILL.md.tmpl` | behavior | `templates/rules/voice.md` line 2; `templates/rules/builder-ethos.md` line 2 | VERIFIED |
| 16 | The rule-edit fixture F2 grew past its ceiling with `**/rules/*.md` in scope | behavior | Measured during the change; no file in the tree records the run | UNAVAILABLE in the tree |
| 17 | A ratchet test forbids a ceiling raise | path | `tests/validation/test_instruction_ceiling_ratchet.py` exists | VERIFIED: path. Behavior not rerun |
| 18 | 21 partials exist; 32 of 121 templates include one | count | `ls templates/skills/partials \| wc -l`; `grep -l '{{> ' templates/skills/*.SKILL.md.tmpl \| wc -l`; `ls templates/skills/*.SKILL.md.tmpl \| wc -l` | VERIFIED: 21, 32, 121 |
| 19 | The six tier 2 partials hold 7,603 bytes | count | `wc -c` on `writing-style`, `voice-banned-vocabulary`, `completeness-scores`, `confusion-protocol`, `clear-the-gate`, `own-and-flag` | VERIFIED: 2041 + 552 + 1817 + 2646 + 295 + 252 = 7603 |
| 20 | Each tier 2 partial except `clear-the-gate` has one including template | count | `grep -l '{{> *<partial>' templates/skills/*.SKILL.md.tmpl` | VERIFIED: `plan` (3), `ai-agents-docs-of-record`, `ai-agents-external-claims`; `clear-the-gate` has 4 |
| 21 | Four partials restate `core` text and are included in skill bodies | behavior | Same grep: `terminal-predicate` 2, `completion-tail-audit` 3, `no-dashes` 5, `user-sovereignty` 1 | VERIFIED: counts. Restatement judged by reading |
| 22 | No partial exists for search before building, boil the lake, or the long user sovereignty text | absence | `ls templates/skills/partials/` | VERIFIED: 21 names listed, none match; `user-sovereignty.mustache` is the 269-byte short form |
| 23 | Three pre-PR gates guard the always-on set: budget sums `.github/instructions/` universal files, corpus claims pins the doctrine numbers, coverage requires scenarios | behavior | `scripts/validation/pre_pr_sequence.py` lines 633, 784, 794; `checks_tooling.py` lines 832 to 837 and 1058 to 1065; `checks_spec.py` lines 143 to 149; `.github/instructions/` holds `core.instructions.md` and `universal.instructions.md` | VERIFIED. Refuting seat finding on the first wording: corrected |
| 24 | ADR-105 put the contract in `builder-ethos.md` | quote | ADR-105 Decision item 1 | VERIFIED |
| 25 | ADR-088 moved eight book rules to one skill and lowered the ratchet | quote | ADR-088 lines 51 and 66 | VERIFIED |
| 26 | Task intent on Sonnet 5.5 scored -0.14 | count | Eval report line 274 | VERIFIED |
| 27 | The registered design names `gpt-5.6-sol`, which was not run | quote | Eval report line 367 | VERIFIED |
| 28 | The `voice` and `builder-ethos` pools measured the seven clauses | quote | Eval report line 369 | VERIFIED |
| 29 | No scenario exercises Ownership, Boil the Lake, Search Before Building or Unattended Runs | quote | Eval report line 385 | VERIFIED |
| 30 | No scenario file mentions the banned word list | absence | `grep -il 'banned\|delve\|vocabulary' tests/evals/rule-scenarios/*.json` | VERIFIED: no file matched |
| 31 | Fixture ceilings drop by 17,900 to 32,100 bytes; `.md` ceiling 83,000 to 34,600 | count | `git diff 8104f11665 HEAD -- scripts/validation/instruction_budget_constants.py` | VERIFIED: F1 17,900; F2 18,500; F3 19,900; F4 21,700; F5 32,100; F6 25,300 |
| 32 | `_durable_live.py` control loads `core.md` and `universal.md` | path | `scripts/eval/_durable_live.py` lines 129 to 130 | VERIFIED |
| 33 | Tests that pinned contract text now read `core` | behavior | `git show --stat d3c2d82df9`: three test files changed | VERIFIED |
| 34 | References changed in `voice`, `universal`, orchestrator templates and one skill | behavior | `git show --stat 0c33e84883` | VERIFIED: `avoiding-manufactured-work` is the skill |
| 35 | `builder-ethos.md` section 4 keeps its header and a two-sentence pointer | quote | `templates/rules/builder-ethos.md` lines 83 to 85 | VERIFIED |
| 36 | `core.md` `### Finding disposition` delegates to `avoiding-manufactured-work`, same sentence | quote | `templates/rules/core.md` lines 35 to 37 against ADR-105 item 4 | VERIFIED: sentence identical |
| 37 | `voice.md` Quick Self-Review entry reads "core.md Terminal Predicate" | quote | `templates/rules/voice.md` line 140 | VERIFIED |
| 38 | `Verify dispatch closure against base` fails on a new rule and is not required | behavior | PR #7730 check reading on d3c2d82df9, 2026-11-26 | VERIFIED on the PR. Not in the tree |
| 39 | 191 sessions, 28 with a `Skill` call, 24 hours before 2026-11-26 | count | Count over the owner's local Claude Code transcripts | UNAVAILABLE in the tree. One machine, one day |
| 40 | Owner reports 400 million tokens an hour and 91 percent cached input | quote | Owner statement in the request for this work | UNAVAILABLE in the tree |
| 41 | gstack requires `preamble-tier` with no default and the build throws without it | behavior | gstack `scripts/resolvers/preamble.ts` lines 70 and 123 to 128, local copy read 2026-11-26 | VERIFIED outside the tree |
| 42 | gstack tier 4 renders the same preamble as tier 3 | behavior | gstack `scripts/resolvers/preamble.ts` piece list, no piece has `minTier` 4 | VERIFIED outside the tree |
| 43 | gstack hoists shared sections because its preamble is about 27,000 characters | quote | gstack `scripts/resolvers/preamble-hoist.ts` header comment | VERIFIED outside the tree |
| 44 | gstack declares the tier as a `preamble-tier` frontmatter key and resolves `{{PREAMBLE}}` | behavior | gstack `scripts/gen-skill-docs.ts` line 741; `scripts/resolvers/preamble.ts` lines 123 to 124, local copy | VERIFIED outside the tree |
| 46 | The skill template grammar allows a partial include and a comment only, no variables | quote | `build/scripts/skill_template_grammar.py` lines 19 to 36 | VERIFIED |
| 47 | Partials may include partials | behavior | `build/scripts/skill_template_grammar.py` `_validate_partial_tree`, lines 228 to 295, recurses into each partial | VERIFIED |
| 48 | The build fails on an include that names a missing partial | behavior | `build/scripts/skill_template_grammar.py` line 280 raises `MissingPartialError`; docstring line 86 maps it to exit 2 | VERIFIED: code read. Not rerun |
| 45 | ADR-108 and ADR-127 titles | quote | `grep '^# ADR' ADR-108-*.md ADR-127-*.md` | VERIFIED |
| 49 | Task intent on Sonnet 5.5 scored -0.01 against no rule; current rule lift +0.13 (p=0.126) | count | Eval report lines 286 to 287 | VERIFIED |
| 50 | The report measured 32,940 bytes at 902278fa50 | quote | Eval report line 4 | VERIFIED |
| 51 | `universal` render grew from 8,879 to 8,886 bytes | count | Rows 1 and 7 | VERIFIED |
| 52 | About 85 percent of sessions invoke no skill | count | (191 minus 28) / 191 from row 39 | VERIFIED arithmetic: 85.3 percent. Inputs UNAVAILABLE in the tree |
| 53 | Quota limits were hit; an earlier diet pass without evals was rejected | quote | Owner statements in the request for this work | UNAVAILABLE in the tree |
| 54 | The eval ran with `EVAL_PROVIDER=claude-cli` through the local gateway | quote | Eval report line 12 | VERIFIED |
| 55 | Every Decision item ships in PR #7730; rollback is one revert | behavior | Branch `feat/always-on-micro-core` holds the four commits after 8104f11665 | VERIFIED: `git log 8104f11665..HEAD` lists 4 commits. Revert not rehearsed |
| 56 | The contract text in `core.md` matches the old `builder-ethos.md` section 4 except two pointer phrases | quote | `diff` of the section at 8104f11665 against `templates/rules/core.md` lines 22 to 59 | VERIFIED: 2 lines differ, lines 2 and 18 of the section |
| 57 | The `.md` budget counts a wider corpus than the two rules | count | `scripts/validation/instruction_budget_constants.py` lines 44 to 47: measured 33,708 bytes | VERIFIED |
| 58 | ADR-105 amendment item 4: `builder-ethos.md` and `voice.md` keep `priority: critical` and scope `paths` | quote | `templates/rules/builder-ethos.md` lines 2 to 3; `templates/rules/voice.md` lines 2 to 3 | VERIFIED |
| 59 | Mean margins against the old rules: `voice` +0.03 and -0.02, `builder-ethos` +0.04 and +0.17 | count | Eval report lines 63, 69, 65, 71 | VERIFIED |
| 60 | The same model answered and judged; the core was tuned on the scenarios; no held-out set | quote | Eval report lines 383 to 384 | VERIFIED |
| 61 | Two rubrics and one sentence changed after the third run | quote | Eval report lines 388 to 389 | VERIFIED: T2 and T7 rubrics; one Task Intent cross-reference |
| 62 | Each pool has three runs on each of two Claude models | quote | Eval report lines 351 to 352 | VERIFIED |
| 63 | `.py`, `.cs` and `.ps1` ceilings drop from 60,000 to 39,500 | count | `git diff 8104f11665 HEAD -- scripts/validation/instruction_budget_constants.py` | VERIFIED |
| 64 | `core.md` declares `task-intent-authorization`; `builder-ethos.md` no longer does | behavior | `grep -c task-intent-authorization` on both templates and on `git show 8104f11665:templates/rules/builder-ethos.md` | VERIFIED: core 1, builder-ethos 0, base builder-ethos 1 |
| 65 | `voice` plus `core` plus `universal` is 28,579 bytes, a 13 percent cut | count | 12817 + 6876 + 8886; (32940 - 28579) / 32940 | VERIFIED: 28579, 13.2 percent |
| 66 | ADR-093 says a clause "failed the admission test for always-on bytes" | quote | ADR-093 line 77 | VERIFIED |
| 67 | ADR-107 line 191 cites `builder-ethos.md` section 4 | quote | ADR-107 line 191 | VERIFIED |
| 68 | The change touches 75 files at d3c2d82df9 | count | `git diff --shortstat 8104f11665 d3c2d82df9` | VERIFIED: 75 files |
| 69 | `FAILURE-MODES.md` entry 12 names `core.md` as the always-on owner | quote | `.agents/governance/FAILURE-MODES.md` lines 550 to 551 and 561 to 562, edited in revision 2; `tests/evals/completion-terminal-runtime-fixtures.json` installs `rules/core.md` and `rules/voice.md` | VERIFIED |
| 70 | Issue #7502 tracks the scenario gap and is open | behavior | `list_issues.py --search`, read 2026-11-26 | VERIFIED: open, "cover the uncovered rules and skills with activation scenarios" |
| 71 | 17,178 bytes is about 4,300 tokens | count | 17178 / 4 | INFERRED: four bytes per token is an assumed ratio, not a measurement |
| 72 | Three of three round 1 reviewers asked to split the preamble tiers out | count | `.project-toolkit/critique/ADR-129-debate-log.md` round 1 | VERIFIED: architect, critic, independent-thinker |
| 73 | An author editing `**/rules/*.md` loads neither `voice` nor `builder-ethos` | behavior | `paths:` lines of both templates, row 15 | VERIFIED |
| 74 | `builder-ethos.md` still states the Precedence Stack and section 3 | path | `grep -n '^## ' templates/rules/builder-ethos.md` | VERIFIED |
| 75 | `voice.md` Unattended Runs holds the Ask First halt rule; Ownership holds the flag-a-secret duty | quote | `templates/rules/voice.md` lines 83 and 91, read by the security seat | VERIFIED |
| 76 | ADR-105 moved two subsection bodies to a skill on 2026-09-15 | quote | ADR-105 Decision item 1, "Amended under epic #5456 M4 (2026-09-15)" | VERIFIED |
| 77 | `core.md` clause 5 states user sovereignty and clause 6 ranks policy above a request | quote | `templates/rules/core.md` lines 17 to 18 | VERIFIED |
| 78 | The report says three gate lines were written before the core results were read; its fourth line is "Negative scenarios are reported apart" | quote | Eval report lines 29 to 34 | VERIFIED. Round 2 analyst finding on the first wording: corrected |
| 79 | The sign rule was registered on 2026-08-03 and applied to finished runs with no new run | quote | `rule-audit-procedure.md` line 209 heading; eval report line 350 | VERIFIED |
| 80 | Six runs reject a cut only at 6 of 6 | count | Two-tailed sign test: 6 to 0 gives 0.031, 5 to 1 gives 0.219; eval report lines 356 to 358 | VERIFIED |
| 81 | Task intent sign count: 0 core wins, 3 old-rule wins, 3 ties, p=0.250 | count | Eval report line 359 | VERIFIED |
| 82 | gstack accepts `preamble-tier` values 1 to 4; ADR-088 and ADR-110 titles as cited | quote | gstack `scripts/resolvers/preamble.ts` lines 124 and 128, local copy; `grep '^# ADR' ADR-088-*.md ADR-110-*.md` | VERIFIED: gstack outside the tree |
