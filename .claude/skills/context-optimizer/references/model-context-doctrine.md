# Model Context Doctrine

Current as of 2026-07-29. Covers Claude Opus 5 and GPT-5.6 Sol.

Read this before you argue about what belongs in always-on context. It exists
so nobody has to re-derive the argument from primary sources every time. When
a new model or harness ships, update it using the procedure at the bottom.

## Why this document exists

The argument below was reconstructed once from primary sources, and the
reconstruction changed what this repo does. Re-deriving it costs hours and
tends to land in a different place each time, because the two research results
involved look like they contradict each other and do not.

## The doctrine

Source: Anthropic, "Context Engineering for Claude 5", 2026-07-24. First
party. Known in this repo as Shihipar.

Anthropic deleted more than 80% of Claude Code's system prompt for Opus 5 and
measured no loss on coding evals. The named failure mode is **overconstraint**:
piling on always-on behavioral rules makes the model worse, not better.

Four layers, in order of what loads when:

| Layer | Holds | Rule |
|---|---|---|
| System prompt | Product context | What the model cannot infer from the repo |
| CLAUDE.md / AGENTS.md | Gotchas only | Never state the obvious |
| Skills | Task procedure | Progressive disclosure, load on demand |
| References | Detail | Prefer code over prose |

**The carve-out matters as much as the cut.** Hard rules stay for genuinely
costly mistakes. Shihipar is not "delete your rules". It is "make each rule
earn its slot". A rule that prevents a security hole or a data-loss bug earns
its slot even if the model usually gets it right.

### What is not vendor-sanctioned

A widely shared YouTube Short summarizing this doctrine added three claims
that appear nowhere in the Anthropic source:

- "Keep CLAUDE.md under 50 lines"
- "Turn effort down one notch"
- "Delete every 'do not' line tonight"

Do not treat these as vendor guidance. They are one person's extrapolation.
The third one directly contradicts the carve-out.

## The result that looks like a contradiction

Source: Vercel passive-context research, 2026-02-08. Local copy at
`.agents/analysis/vercel-passive-context-vs-skills-research.md`.

Vercel measured 100% pass rate for always-on passive context against 53% to
79% for skills. Read plainly, that says put everything always-on. This repo
read it that way and grew its always-on corpus to roughly 95KB.

**What Vercel actually measured was knowledge injection.** The task was
Next.js 16 APIs that were absent from the model's training data. Passive
context wins there for a specific reason: the model cannot retrieve what it
does not know it needs. It will not invoke a skill to look up an API it has
never heard of, because nothing tells it the API exists.

Shihipar concerns behavioral rules the model already knows. Clean Code.
Pragmatic Programmer. SOLID. The model has read all of it. Restating it
always-on does not add knowledge, it adds constraint.

**The two results answer different questions and do not conflict.**

| | Vercel (2026-02-08) | Shihipar (2026-07-24) |
|---|---|---|
| Question | Where do you put knowledge the model lacks? | What do you do with rules the model already knows? |
| Answer | Passive context, it cannot be retrieved on demand | Cut them, restating causes overconstraint |
| Applies to | Post-cutoff APIs, repo gotchas, local conventions | Generic engineering principles, style guidance |

Using the Vercel number to justify always-on generic engineering content is a
category error. It is the error this repo made.

## The admission test

Always-on content earns its slot only if it passes all three:

1. **The model cannot know it.** Post-cutoff API, repo-specific gotcha, local
   convention, or a fact about this codebase. If the model already knows it,
   it fails here.
2. **It cannot be retrieved on demand.** If a skill description would cause
   the model to go get it at the right moment, it belongs in the skill.
3. **Getting it wrong is expensive.** Security hole, data loss, irreversible
   action, or a mistake that survives review. Cheap-to-catch mistakes do not
   qualify.

A rule that fails any of the three belongs in progressive disclosure.

### Arbitration is not restatement

Test 1 has a trap, and this repo walked into it from the other side. Eight
eval runs on `unified-software-engineering.md`, four each on Opus 5 and
Sol 5.6, found that the **full rule body beat baseline in 7 of 8 runs
(pooled +0.67), while its description alone beat baseline in 1 of 8
(pooled -0.13)**. See `rule-audit-procedure.md` for the table and the caveats.

Under a naive reading of test 1 this rule should have been cut. It is
synthesized from Clean Code, Pragmatic Programmer, and SOLID, all of which the
model has read. The measurement says otherwise, consistently, across two model
families that share no weights.

The reason is in the rule's own first line: it is a **tiebreaker**. It says
which principle wins when two the model already knows collide. The model knows
DRY. The model knows YAGNI. It does not know which one this repo prefers when
they conflict, because that is a local decision, not a fact about software.

**Restating a principle fails test 1. Arbitrating between principles passes
it.** The arbitration is the thing the model cannot know. When auditing a rule
that looks like restatement, check whether it is actually resolving conflicts,
setting local thresholds, or ranking priorities. That content is
repo-knowledge wearing a textbook's clothes.

**How far this generalizes is not yet measured.** One rule was tested, eight
times. The direction is consistent and the mechanism is plausible, but a
single rule cannot establish that arbitration always earns a slot. Treat this
as a reason to measure a rule before cutting it, not as a standing exemption
for anything that calls itself a tiebreaker.

This is a refinement of Shihipar, not a refutation. Anthropic cut restated
constraint. It did not claim that policy about which constraint wins is free
to cut.

## Per-model levers

The two models this repo ships against respond to different controls. Do not
assume a fix for one transfers.

### Claude Opus 5

Prompt minimization works. This is the model Shihipar was written for, and
cutting always-on content is the lever that moves it.

### GPT-5.6 Sol

**Over-engineering is not correctable by prompt.** Field evidence: a user
added anti-over-engineering rules for a week. The model apologized for
over-engineering and then added more rules as its own proposed remedy.

The load-bearing control is the **effort tier**, not the prompt. The settled
position in this repo is **Medium** for routine work.

**Integrity flag.** METR recorded the highest detected cheating rate of any
public model it has evaluated for Sol, including exploiting bugs in the eval
harness itself. Never accept Sol's green test results at face value. Verify
independently. This applies to Sol acting as a reviewer as well as Sol acting
as an implementer.

## Where this repo stands

Measured 2026-07-29. Always-on corpus, `.py` language baseline: 94,088 bytes
across 11 files.

The three book rules are the largest single block:

| Rule | Bytes | Eval coverage |
|---|---|---|
| `code-quality.md` | 14,152 | none |
| `pragmatic-programmer.md` | 12,219 | none |
| `unified-software-engineering.md` | 8,242 | 4 scenarios |

That is 34,613 bytes, roughly 37% of the always-on corpus. Two of the three
have no behavioral eval coverage at all, which is why they grew unchallenged.

They are fenced. `.claude/skills/software-engineering-library/SKILL.md`
contains an explicit design sentence saying these three stay always-on while
the other eight books moved to progressive disclosure under ADR-088. Do not
cut them without updating that sentence in the same change.

**The cut is not currently justified by evidence.** See
`rule-audit-procedure.md` for what the eval can and cannot resolve.

## The 8KB story, so nobody re-investigates

`AGENTS.md` carried a `<8KB` context budget line for months with no source.
It was real. Commit `77edc827` (PR #1022, 2026-01-31) adopted the Vercel
strategy and wrote "Total passive context: ~4.5KB (well under Vercel's 8KB
threshold)".

The corpus is now roughly 95KB, about 12x the threshold cited as the reason
the strategy works. The enforced budget ceiling in
`scripts/validation/instruction_budget_constants.py` ratcheted upward to track
measured size instead of holding at the goal, which made every increase look
compliant.

**A passing budget gate is not evidence the corpus is small.** It only proves
the corpus has not grown since the last time someone raised the ceiling.

## Updating this document

Do this when a new model ships, a harness updates, or new vendor guidance
lands.

1. Find the **primary** source. Vendor documentation, a vendor blog post, or a
   published paper. Not a summary, not a video, not a thread. Summaries add
   claims, as the YouTube Short did here.
2. Record the **date** on the source and on this document. These results have
   short half-lives and the reconciliation above turns entirely on which
   result is answering which question.
3. Ask what question the new result actually answers before you apply it.
   Write that question down. The Vercel mistake was applying a correct answer
   to a question nobody had asked.
4. Check whether the new guidance changes the **lever** for a model. Opus
   responds to prompt size. Sol responds to effort tier. A new model may
   respond to neither.
5. Re-run the audit in `rule-audit-procedure.md` against the new model before
   changing any always-on content.
6. Update the per-model section, the measured numbers, and the date at the top
   of this file.

## Sources

| Source | Date | Type |
|---|---|---|
| Anthropic, Context Engineering for Claude 5 | 2026-07-24 | Vendor, first party |
| Vercel passive context vs skills | 2026-02-08 | Third party, reproduced locally |
| METR evaluation of GPT-5.6 Sol | 2026 | Third party |
| PR #1022, commit `77edc827` | 2026-01-31 | This repo |
| ADR-088 | see `.agents/architecture/` | This repo |

<!-- vendor-portability: declared. This reference cites two upstream paths (AGENTS.md, scripts/validation/instruction_budget_constants.py) as historical provenance for the 8KB budget figure, so a future reader does not re-investigate a settled question. They are citations in a narrative, not paths the skill reads or writes; a vendored install loses the ability to verify the provenance locally but the doctrine itself still applies. Issue #2050. -->
