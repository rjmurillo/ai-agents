# ADR-105 Amendment 2026-10-13: Debate Log

**ADR**: `.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md`
**Amendment**: Decision item 1 records that section 4's `### Precedence` line now ranks mandatory safety and repository policy above the current user request. The Negative section and the Consensus section are updated to match.
**Triggering context**: issue #5535, `builder-ethos.md` ranks a user request above mandatory safety and repository policy on `main`.
**Date**: 2026-10-13
**Panel**: full panel (architect, critic, independent-thinker, security, analyst, high-level-advisor). The change edits a rule other gates read: `tests/test_completion_terminal_contracts.py` pins section 4, and the pre-PR `Always-on Corpus Claims` and `Instruction Budget (always-on)` gates read `builder-ethos.md`.

## Mechanism and its limit

One implementing agent ran all six seats in sequence, each from a written brief, each required to check a primary source and to say so when it found nothing. The implementing agent had no way to dispatch separate fresh-context agents in this run. The 2026-09-03 log for ADR-105 used six separate agents. This log is weaker evidence than that one: the seats share one context and one author, so they are not independent. The owner delegated the design choice on 2026-10-11, and the pre-PR gates and the PR review are the independent checks.

## Phase 0: Related work checked

| Item | State | Relevance |
|---|---|---|
| Issue #5535 | Open | The defect and its three options |
| Issue #5404 | Closed | Origin of the literal user-first precedence text |
| PR #5506 | Merged | Shipped the user-first order to `main` on 2026-09-03 |
| PR #5433 | Closed, not merged | Carried the owner's swap in commits `e84f0b603`, `5e152e4b7`, `2c1b22df3` |
| Comment `3900588149` | Fetched with `gh api` on 2026-10-13 | Owner approves the swap, authored by `rjmurillo` on 2026-09-01 |
| ADR-105 debate log, 2026-09-03 | On `main` | Recorded this risk as open and tracked on #5535 |
| ADR-105 amendment log, 2026-09-15 | On `main` | Precedent for amending ADR-105 in place without a status change |

## Round 1

### Agent positions

| Agent | Position | Main finding |
|---|---|---|
| architect | Accept with P1 | Three statements must agree. The first draft fixed two and left the stack's item 1 saying only "User Sovereignty wins". |
| critic | Accept with P1 | "Mandatory policy" was undefined, so the new order could not be tested or applied. |
| independent-thinker | Accept with P2 | Option 2 (carve-out list) drifts as rules change. Option 1 needs no list to stay true. |
| security | Accept with P1 | The old order demoted `universal.md` MUST 1, MUST 7, MUST NOT 1, and MUST NOT 2. The new order must name what it protects. |
| analyst | Accept with P1 | The owner's commits touch the skill and section 3 only. The ADR must say section 4 and the stack needed their own edits. |
| high-level-advisor | Accept | Ship option 1. The owner chose it on 2026-09-01 and four reviewers asked for it. |

### What each seat verified

#### Architect

- Read the shipped `templates/rules/builder-ethos.md` at `origin/main` (`65d769846`) and found the three statements: Precedence Stack item 1, the section 3 opener, and the `### Precedence` line.
- Confirmed the ADR quotes the precedence line verbatim in Decision item 1, so the ADR must change with the rule.
- Confirmed `status: accepted` stays. The 2026-09-15 amendment set the precedent: an in-place amendment with its own log and no status churn.

#### Critic

- Checked the six acceptance criteria on issue #5535 against the diff, one by one.
- Found the term "mandatory safety/repository policy" has no referent anywhere in the file. Added a one-sentence definition to section 4: the MUST and MUST NOT items in `universal.md` and `security.md`, and the `AGENTS.md` Never list.
- Checked the definition against `universal.md`, `security.md`, and `AGENTS.md`. None of their MUST, MUST NOT, or Never items contains an "unless the user" exception.

#### Independent-thinker

- Argued the strongest case for options 2 and 3.
- Option 3 (keep the order, record why) fails on the record: the owner called the order wrong, and Devin, CodeRabbit (two comments), and Copilot each raised it unprompted.
- Option 2 (user-first plus a carve-out) needs an enumerated list of protected policies. A list drifts the first time a rule is added. Option 1 states one comparison, and the definition above names sources, not items.
- Conceded option 1 also needs the source-named definition, so the two options end up close. The ordering still reads as policy-first at the point where a reader looks for it.

#### Security

- Listed what the old order demoted: `universal.md` MUST 1 (no direct commit to `main`), MUST 7 (no secrets), MUST NOT 1 (no force-push), MUST NOT 2 (no hook or signing bypass), and the `AGENTS.md` Never list.
- Confirmed the new definition covers every item in that list.
- Raised the ingested-content risk the 2026-09-03 log recorded: an issue body or fetched page read as the "current user request". The new order bounds it, because policy now outranks whatever is read as the request.

#### Analyst

- Fetched comment `3900588149` with `gh api` and compared it character for character with the issue's quote. It matches.
- Ran `git cat-file -t` on the three owner commits (all `commit`) and `git merge-base --is-ancestor` against `origin/main` (none on `main`).
- Ran `grep` for the precedence chain across the repository. It appears in `templates/rules/builder-ethos.md`, its five generated copies, the new test, and the ADR. The `avoiding-manufactured-work` skill carries no chain, only a pointer to section 4.
- Ran `grep` over `tests/evals/rule-scenarios/builder-ethos.json`. Its five scenarios cover section 5 (Reasoning Discipline) and none grades precedence.

#### High-level-advisor

- Ruled the shape minimal: three sentences in the rule, one definition, one test file, one ADR amendment.
- Ruled the skill edit from `e84f0b603` unnecessary, because the skill no longer states an order. Cherry-picking it would add text the acceptance criteria say should not exist.

## Phase 2: Consolidation

### Consensus points

- Option 1 is the right choice and no seat dissents.
- One order, one definition of "mandatory policy", and a test across every generated copy.
- The ADR is amended in place and keeps `status: accepted`.

### Conflict and ruling

**Conflict**: whether to also cherry-pick `e84f0b603` into the skill, as the owner's comment describes.

- **architect**: the skill should agree with the canonical order.
- **high-level-advisor and analyst**: the skill already carries no order. Agreement is satisfied by absence, and a test can pin that.
- **Ruling**: absence. `test_skill_carries_no_ordering_of_its_own` fails if any skill copy grows its own chain or the rejected order.

### Anti-pattern check

- **No Pass Through**: every seat named a source it read or a command it ran.
- **No Copy Edit**: findings concerned an undefined term, a missing edit, and a drifting alternative.
- **No Siding**: the one conflict was resolved on the skill's actual text.
- **No Groundhog Day**: each Round 1 finding became one edit and was re-checked in Round 2.
- **Independence limit**: the seats share a context. See "Mechanism and its limit".

## Phase 3: Resolution

1. **Stack item 1 and section 3** gained the same clause: "but never mandatory policy (section 4)." The Instruction Bytes fixture F1 ceiling (276000) left 260 bytes of headroom, so the first, longer wording (+394 bytes) failed the gate and was cut to +258 bytes.
2. **Section 4** now ranks policy above the current request and defines mandatory policy by source.
3. **Test added**: `tests/test_builder_ethos_precedence_order.py` asserts the same chain on the canonical template, five generated copies, and the ADR. It asserts the rejected chain is absent, the carve-out appears twice per copy, and no skill copy carries a chain. Mutation check: flipping the chain in `.github/instructions/builder-ethos.instructions.md` failed 4 tests.
4. **ADR-105** updated in Decision item 1, the classification-order paragraph, the Negative section, and the Consensus section.
5. **Owner decision recorded** with the rejected options and the reason for each.

## Round 2: convergence

Each seat re-read the diff against its Round 1 finding.

### Final positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Three statements agree; ADR quotes the shipped line. |
| critic | Accept | The definition is testable; all six acceptance criteria map to a hunk or a test. |
| independent-thinker | Accept | Disagree and commit on one point: a source-named definition is close to option 2's list. The result is shorter and does not drift. |
| security | Accept | Every item the old order demoted is now protected. Ingested-content risk stays open and is bounded. |
| analyst | Accept | Every citation was fetched or grepped, not recalled. |
| high-level-advisor | Accept | Skill left alone. Ship. |

## Issue Resolution Summary

| Priority | Count | Resolved | Deferred |
|---|---:|---:|---:|
| P0 | 0 | 0 | 0 |
| P1 | 4 | 4 | 0 |
| P2 | 3 | 2 | 1 |

The deferred P2: the definition covers `universal.md`, `security.md`, and the `AGENTS.md` Never list. It does not cover MUST items in path-scoped rules such as `python.md`. A user request can still lower those. That scope is deliberate and the owner can widen it in a later change.

## Strategic Assessment

- **Chesterton's Fence**: Pass. The user-first order came from #5404's literal text. Review rejected it in four places, and the owner approved the swap.
- **Path dependence**: Pass. The change is one text edit and one test, so reverting is a single revert.
- **Core vs context**: Pass. This is core behavior of an always-on rule.
- **Second-system effect**: Pass. No new framework. One clause repeated twice, one definition, one test file.

## Final verdict

Amendment accepted. ADR-105 stays `accepted`. Option 1 is taken. The remaining risks are the undefined "current user request" for ingested content, which the new order bounds, and the path-scoped rule MUST items, which the definition leaves out on purpose.
