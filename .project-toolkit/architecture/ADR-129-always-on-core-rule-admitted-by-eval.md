---
id: ADR-129
status: accepted
date: 2026-11-26
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-02-26
---

# ADR-129: An Always-On Core Rule, Admitted by Eval

## Context

Three rules loaded on every request in every session: `voice`, `builder-ethos`
and `universal`. Each declared `paths: ["**"]` and `priority: critical`.
At 8104f11665 (2026-11-26) their Claude Code renders held 32,940 bytes:
`voice` 12,817, `builder-ethos` 11,244 and `universal` 8,879. The eval report
measured the same total at 902278fa50 (2026-11-25).

The owner reports about 400 million tokens an hour across subscriptions, with
cached input at 91 percent of the last seven days. Every always-on byte is paid
on every request of every session, by every agent and subagent.

Three forces pull against a plain cut.

1. **The rules carry behavior that works.** ADR-105 put the Task Completion
   Contract in `builder-ethos` because every role must load it on every turn.
   A cut that drops it reopens the failure ADR-105 closed.
2. **Skills do not reach most sessions.** The owner's Claude Code transcripts
   modified in the 24 hours before 2026-11-26 hold 191 sessions. 28 of them
   hold a `Skill` tool call. A rule that lives only in a skill misses about 85
   percent of sessions. This count comes from one machine, not from the repo.
3. **Nobody had measured which clauses earn their place.** The always-on set
   grew by argument. No record said which clause changes an answer.

A user can enter through any skill, or through none. A rule placed in one
router skill reaches only sessions that start there.

### Decision drivers, in priority order

1. Keep measured behavior. A cut that fails the gate does not ship.
2. Cut bytes paid on every request.
3. Keep one owner for each rule text.

Driver 1 outranks driver 2. Where the eval is silent, driver 2 decides, and the
record names the loss.

## Decision

### 1. The always-on set is `core` and `universal`

`core` is a new rule that loads on every path, with `priority: critical`. It
holds seven one-paragraph clauses and four sections: Task Completion Contract,
Task Intent, Unattended Runs, and Completion-Tail Audit. Its Claude Code render
was 6,876 bytes at d3c2d82df9 (2026-11-26); admitting Unattended Runs and the
Ask First branch halt raises the current render to 7,129 bytes.

`universal` stays always-on and whole. One pointer line in it now names `core`,
so its render grew from 8,879 to 8,886 bytes.

The always-on set falls from 32,940 bytes to 15,762 bytes at d3c2d82df9
(2026-11-26). That is 17,178 bytes fewer on every request, a 52 percent cut.

### 2. An eval gates what stays in the always-on set

Text that replaces always-on text must clear this gate:

- positive scenarios: candidate minus current is -0.20 or better, per rule and model;
- no positive scenario falls more than 1.00 below current;
- candidate minus no rule stays above zero;
- the registered sign rule in `rule-audit-procedure.md` does not favor current.

The report says the first three lines were written before the core results
were read. `rule-audit-procedure.md` registered the sign rule on 2026-08-03.
The report applied it to the finished runs, with no new run.

Evidence for this change is in
`evals/reports/rule-activation-always-on-core-2026-11-26.md`. Three results
shaped the set:

- Seven clauses alone failed the completion tail at -0.87 and -0.78. So `core`
  carries the Task Completion Contract, Task Intent and Completion-Tail Audit.
- A seven-clause replacement for `universal` failed at -0.28 and -0.26, and lost
  the sign count in 6 of 6 runs. So `universal` stays whole.
- The gate did not reject the cut of `voice` and `builder-ethos`. The mean
  margins against the old rules were +0.03 and -0.02 for `voice`, and +0.04
  and +0.17 for `builder-ethos`. The sign counts were 5 to 1 and 4 to 2 for
  the core. Six runs can reject a cut only at 6 of 6, so the sign rule has
  little power here. The mean margins carry the case.

**Exception: measured candidate differs from shipped core.** The `voice` and
`builder-ethos` eval pools measured the seven-clause candidate. The shipped
`core` adds the Task Completion Contract, Task Intent, Completion-Tail Audit and
Unattended Runs sections. Those sections were not part of the candidate the
voice and builder-ethos pools scored, and the Unattended Runs section was not
scored in any pool.

- Scope: the cut of `voice` and `builder-ethos` from the always-on set, and
  nothing else.
- Reason: no paid rerun on the shipped `core` was run for this change. The
  margins above are evidence about the candidate, not the shipped text.
- Reversal: a rerun of the voice and builder-ethos pools on the shipped `core`
  decides. If it fails any gate line above, revert PR #7730, as Rollback
  states. Restoring only the prior always-on `voice` (13,659 bytes) and
  `builder-ethos` (11,187 bytes) rules, as main holds them at a09c8807a4
  (2026-11-28), does not fit: the always-on `.md` corpus had 670 bytes of
  headroom under its 34,600-byte ceiling at 5f0809ccb9 (2026-11-28). The review
  date of this record is the deadline for that rerun.

**Exception: Unattended Runs.** No eval pool scored the `## Unattended Runs`
section. It stays in `core` because cutting it removes the only always-on halt
for Ask First work in a headless run.

- Scope: the `## Unattended Runs` section of `core`, and nothing else.
- Reason: the section carries safety-adjacent continuity from the former
  always-on `voice` rule. Without it, a scheduled or headless branch that hits
  an architecture, ADR, breaking-change, or security decision can guess and
  continue. That risk was not measured by any pool.
- Reversal: the scenario work tracked by issue #7502 measures the section. If
  it shows no lift over no rule on both models, or fails the gate lines above,
  cut it or rewrite it. The review date of this record is the deadline for that
  measurement.

This evidence is exploratory. The core text changed after scored runs, and no
held-out scenario set exists. The Negative section lists each limit.

**A gate miss keeps text only as a named exception.** The exception states its
scope, its reason and its reversal trigger in the deciding record.

**Exception: Task Intent.** Task intent on Sonnet 5.5 scored -0.01 against no
rule, 0.01 under the third gate line.

- Scope: the `## Task Intent` section of `core`, and nothing else.
- Reason: the old rule's own lift there is +0.13 (p=0.126). These scenarios
  show no reliable lift from either text, so they cannot support a cut. The
  sign count was 0 for the core, 3 for the old rules and 3 ties (p=0.250).
- Reversal: a rerun with more task intent scenarios decides. If the section
  still shows no lift over no rule on both models, cut it or rewrite it. The
  review date of this record is the deadline for that rerun.

**The gate is one-sided.** It tests text that stays or replaces. Text with no
scenario can leave the always-on set untested. This record accepts that
asymmetry for the byte cut, and names each such section as an unmeasured loss.
A scenario that shows a loss past the gate lines re-admits the section.

Outside a named exception, unmeasured text does not enter the always-on set on
argument alone.

### 3. `voice` and `builder-ethos` become skill-authoring sources

Both rules keep their full text and `priority: critical`. They load only on
skill authoring paths: `**/SKILL.md`, `**/skills/**/*.mustache` and
`**/*.SKILL.md.tmpl`.

They are the source text for the skill partials under
`templates/skills/partials/`. A skill author sees the full rule while editing
the files that inject it.

They do not load on `**/rules/*.md`. With that path the rule-edit routing
fixture F2 grew past its ceiling during this change. The ratchet in
`tests/validation/test_instruction_ceiling_ratchet.py` forbids a raise. So an
author editing a rule file loads neither rule.

### 4. `core` owns the Task Completion Contract and task intent

ADR-105 named `builder-ethos.md` section 4 as the owner of the contract. The
owner is now `core.md`, section `## Task Completion Contract`. The always-on
invariant does not change. The text matches the old section except two pointer
phrases. ADR-105 carries an amendment that records the move.

This is an amendment, not a superseding record. ADR-105 decided that the whole
contract sits on the always-on rule path. That decision stands. Only the file
that carries the contract changed. ADR-105 moved two subsection bodies the same
way on 2026-09-15.

`voice.md` keeps the long form of the Completion-Tail Audit for skill authors.
`core.md` carries the always-on form.

`core.md` also declares the `task-intent-authorization` capability that
`builder-ethos.md` declared before. The capability graph still has one owner.

### 5. What this record does not decide

- It does not decide how skills carry the text that left the always-on set.
  The next section records a direction only.
- It does not shorten skill descriptions. That is a separate change with its own eval.
- It does not cut `universal`, or change any rule scoped to a file type.
- It does not change hook output, memory recall, or session-start context.

## Direction, Not Decided: Skill Preamble Tiers

This section binds nothing. A later record decides it, with its own eval.

The intended path follows the gstack model. Common text is injected into every
skill that needs it, because the entry point is unknown.

- A skill template would include one composite partial:
  `{{> preamble-tier-2}}` or `{{> preamble-tier-3}}`.
- A template with no such include is tier 1. It gets `core` and nothing more.
- An include must name its tier. No include form picks a tier by default.
- A tier follows the skill's role, not its author's preference.

| Tier | Role | Preamble would add |
|---|---|---|
| 1 | Lookup, reference and single-tool skills | Nothing |
| 2 | Skills that write prose or artifacts, or run a workflow | `writing-style`, `voice-banned-vocabulary`, `completeness-scores`, `confusion-protocol`, `clear-the-gate`, `own-and-flag` |
| 3 | Planning, review and ship skills | Tier 2, plus search before building, boil the lake and user sovereignty detail |

The six tier 2 partials exist and hold 7,603 bytes at d3c2d82df9 (2026-11-26).
The tier 3 additions have no partial yet.

gstack declares the tier as a `preamble-tier` frontmatter key and resolves a
`{{PREAMBLE}}` placeholder. It declares four tiers, and its tier 4 renders the
same preamble as tier 3. This repo's template grammar allows two tags only: a
partial include and a comment. It has no variables. Partials may include
partials, and the build fails on a missing partial. So the tier can live in
the name of the included partial, with no frontmatter key and no grammar change.

The deciding record must supply what this section lacks:

- a byte ceiling for each tier's composite;
- the tier of each of the 121 skill templates;
- a gate threshold for the tier eval, set before the scores are read;
- a test for when a partial restates `core`;
- the render choice, inline or hoisted. gstack hoists because its preamble is
  about 27,000 characters.

## Prior Art Investigation

### What Currently Exists

- ADR-105 (accepted) put the whole completion contract in
  `builder-ethos.md` so every role loads it on every turn.
- ADR-088 (accepted) moved eight book rules out of the always-on set
  into one skill, and lowered the instruction budget ratchet in the same change.
- ADR-093 (accepted) cut a proposed clause because it "failed the admission
  test for always-on bytes". That test was a judgment. This record makes it a gate.
- `templates/skills/partials/` holds 21 partials. 32 of 121 skill templates
  include at least one, as of d3c2d82df9 (2026-11-26).
- Three pre-PR gates guard the always-on set. `Instruction Budget (always-on)`
  sums the language-universal files under `.github/instructions/`.
  `Always-on Corpus Claims` pins the doctrine document's numbers to that corpus.
  `Rule Activation Coverage` requires a scenario for each rule.

### Historical Rationale

ADR-105 rejected a contract split across a rule and a skill. A skill loads on
demand, so a role that never opens it never sees the predicate. That reasoning
still holds, and this record keeps the contract always-on.

The always-on set grew for the same reason each time: a rule that is not loaded
cannot be obeyed. Each addition was argued, not measured.

### Why Change Now

Token spend hit quota limits on several subscriptions. A first diet pass
compressed rule text without evals, and the owner rejected it as unmeasured.
The eval harness can now run with `EVAL_PROVIDER=claude-cli` through the
owner's local gateway, so the measurement needs no separate API account.

## Rationale

### Alternatives Considered

| Alternative | For | Against |
|---|---|---|
| Keep three always-on rules | No behavior risk, no new record | 17,178 bytes more on every request, with no evidence most of it changes an answer |
| No always-on rules; all text in skills | Largest cut | About 85 percent of sessions invoke no skill and would load no rule text |
| Full rule text in one router skill (`autoplan`) | One copy to maintain | Users enter through any skill or none, so most sessions miss it |
| Seven clauses only | Smallest core | Failed the completion tail gate at -0.87 and -0.78 |
| Compress all three rules in place | Keeps structure | A seven-clause `universal` failed the gate; compression without evals was rejected earlier |
| Keep `voice` always-on; replace only `builder-ethos` with `core` | Keeps the banned word list and Ownership on every request | The set would hold 28,579 bytes, a 13 percent cut; the gate did not reject the `voice` cut |
| Load `voice` on every `**/*.md` edit | Prose edits keep the full rule | Adds 12,817 bytes to the `.md` budget this change cut; no scenario measures the gain |
| Core plus `universal`; skill delivery left to a later record (chosen) | Measured cut; contract stays always-on; no unbuilt design is bound | Five sections leave unmeasured, with no delivery path yet |
| Core plus `universal`, with tiered preambles decided now | One record covers both halves | The tiers are unbuilt and unmeasured; three of three first-round reviewers asked for the split |

### Trade-offs

The chosen shape trades depth on every request for bytes on every request.

Four sections leave the always-on set unmeasured: Ownership, Boil the Lake,
Search Before Building and the banned word list. The report names the first
three as unexercised. No scenario file under `tests/evals/rule-scenarios/`
mentions the banned word list. So the eval cannot show a loss or rule one out.
Issue #7502 tracks the scenario gap. Unattended Runs stays in the always-on set
by the named exception above.

The loss has no end date in this record. A session that invokes no skill never
loads those sections again. A skill session loads them only where a template
already includes the partial.

## Consequences

### Positive

- 17,178 fewer always-on bytes on every request, in every agent and subagent.
  At four bytes per token that is about 4,300 tokens. The ratio is an estimate.
  The share of the owner's hourly token use is not measured.
- The six routing fixture ceilings each drop by 17,900 to 32,100 bytes.
- The always-on `.md` budget ceiling drops from 83,000 to 34,600 bytes. That
  budget counts every instruction file that applies to a `.md` edit, not only
  the two always-on rules.
- The `.py`, `.cs` and `.ps1` budget ceilings each drop from 60,000 to 39,500 bytes.
- The completion contract stays always-on, as ADR-105 requires.
- Admission to the always-on set now has a stated, repeatable gate.

### Negative

- Four sections leave the always-on set unmeasured, with no end date (see
  Trade-offs). Each tier 2 partial except `clear-the-gate` has one including
  template at d3c2d82df9 (2026-11-26), so most skill sessions lose them too.
- One of the four sections carries security-adjacent text: Ownership says to
  flag a secret seen in code. Unattended Runs also carries security-adjacent
  text, but it stays in `core` by the named exception above and keeps the Ask
  First branch halt. The Ask First list in `AGENTS.md` and the no-secrets rules
  in `universal` and `core` still load on every request.
- Task Intent stays by exception, not by gate (item 2). On Sonnet 5.5 it also
  scored -0.14 against the old rules. That is inside the -0.20 margin, and it
  is a real cost.
- The evidence is exploratory. The core was tuned on the scored scenarios, and
  no held-out set exists. Two rubrics and one sentence changed after the third run.
- The same model wrote the answers and judged them.
- The six sign runs are three repeats on each of two Claude models. They are
  not six independent samples. The registered design also names `gpt-5.6-sol`,
  which was not run.
- The `voice` and `builder-ethos` pools measured the seven clauses, not the
  shipped core with three sections. The shipped core also differs from the
  scored text by one reworded sentence.
- An author editing a rule file loads neither `voice` nor `builder-ethos` (item 3).
- The change touches 75 files at d3c2d82df9 (2026-11-26), most of them generated.
- `Verify dispatch closure against base` fails on any new rule, because the rule
  adds generated symlinks. It is not a required check.

### Neutral

- Tests that pinned contract text in `builder-ethos` now read `core`.
- Lookup of the contract by rule name changes from `builder-ethos` to `core` in
  `voice`, `universal`, the orchestrator templates and one skill.
- ADR-107 line 191 and ADR-105's older sections still name `builder-ethos.md`
  section 4. They record history. The ADR-105 amendment says how to read them.

## Impact on Dependent Components

| Component | Impact |
|---|---|
| `templates/rules/core.md` | New always-on rule; owns `task-intent-authorization` |
| `templates/rules/voice.md`, `builder-ethos.md` | `paths:` narrowed to skill authoring files |
| `scripts/validation/instruction_budget_constants.py` | Always-on membership and all ten ceilings updated |
| `scripts/eval/_durable_live.py` | The `current` control loads `core.md` and `universal.md` |
| `.agents/governance/FAILURE-MODES.md` | Entry 12 names `core.md` as the always-on owner |
| ADR-105 | Amended: owner of the contract is `core.md` |

## Implementation Notes

Every item of this Decision ships in PR #7730. `implemented` flips to `true`
when that PR merges.

Review this record by 2027-02-26. By then the five unmeasured sections have
scenarios or a recorded reason, and the Task Intent exception has its rerun.

Rollback is one revert of PR #7730, which merges as one squash commit. No data
format changes. The revert raises the `.md` ceiling from 34,600 back to 83,000,
so `test_no_ceiling_rose_against_the_base_ref` fails on it until the owner
approves the raise and the commit body says why (issue #4345). The revert also
removes the `rules` and `instructions-github` link exemption in ADR-101, so a
rule link added after the revert fails dispatch closure again. Putting one rule
back alone must fit the lowered ceilings, because the ratchet forbids a raise.

## Related Decisions

- ADR-105: Terminal-State Completion Contract. Amended by this record.
- ADR-088: Progressive Disclosure for Book-Derived Rules. The earlier always-on cut.
- ADR-093: the earlier, informal admission test for always-on bytes.
- ADR-107: its line 191 cites the contract's old home.
- ADR-108: Template-Owned Skill Files. Partials render through templates.
- ADR-110: the capability graph. `core` now owns `task-intent-authorization`.
- ADR-127: Workflow Skills Are Script Drivers. Evals gate skill rewrites.

## References

- `evals/reports/rule-activation-always-on-core-2026-11-26.md`
- `src/claude/skills/context-optimizer/references/rule-audit-procedure.md`
- PR #7730 and issue #7502
- gstack `scripts/resolvers/preamble.ts` and `preamble-hoist.ts`, read 2026-11-26
