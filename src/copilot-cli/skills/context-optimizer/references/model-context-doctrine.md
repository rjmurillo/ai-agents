# Model Context Doctrine

Current as of 2026-08-03. Covers Claude Opus 5 and GPT-5.6 Sol.

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

Source: Vercel, "AGENTS.md outperforms skills in our agent evals", published
January 27, 2026 by Jude Gao. Local analysis at
`.agents/analysis/vercel-passive-context-vs-skills-research.md`, whose own
`Date: 2026-02-08` header is when this repo wrote the analysis, not when
Vercel published. Cite the January date when citing the finding.

Vercel measured 100% pass rate for always-on passive context against 53% to
79% for skills. Read plainly, that says put everything always-on. This repo
read it that way and grew its always-on corpus to a peak of 9 rules and
roughly 84KB. PR #4424 and the `lsp-first` rescope narrowed two of them,
leaving 7 rules and roughly 70KB, with a Python edit pulling in roughly 99KB.

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
(pooled -0.14)**. See `rule-audit-procedure.md` for the table and the caveats.

Under a naive reading of test 1 this rule should have been cut. It is
synthesized from Clean Code, Pragmatic Programmer, and SOLID, all of which the
model has read. **The measurement does not license cutting it.** The sign is
consistent across two sets of runs whose result files carry different model
identifiers, but only 3 of 8 `full - description` gaps clear the ~1.0 noise
floor this document's own variance section establishes. Read that as: the
conservative policy blocks the cut, not as proof the body earns its slot. Two
caveats on the models: attribution rests on run filenames rather than anything
the artifact records (issue #3956), and the provider supplies rule text as a
user message, so this measures priming, not the loading path production uses.

The likely reason is in the rule's own first line: it is a **tiebreaker**. It
says which principle wins when two the model already knows collide. The model
knows DRY. The model knows YAGNI. It does not know which one this repo prefers
when they conflict, because that is a local decision, not a fact about
software. **The eval did not isolate that.** The `full` cell differs from
`description` in arbitration content, length, ordering, and concrete examples
all at once. Any of those could carry the effect. Testing the mechanism means
holding length fixed and varying only whether the text arbitrates.

**Restating a principle fails test 1. Arbitrating between principles is the
leading hypothesis for what passes it.** The arbitration is the part the model
cannot know. When auditing a rule that looks like restatement, check whether it
is actually resolving conflicts, setting local thresholds, or ranking
priorities. That content is repo-knowledge wearing a textbook's clothes.

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

**Over-engineering resists prompt correction.** Field evidence, one user, one
week: they added anti-over-engineering rules, and the model apologized for
over-engineering and then proposed adding more rules as its own remedy. That
is a single uncontrolled trial and an anecdote, not a measurement. It is
recorded because the failure mode is expensive and the anecdote is the only
evidence anyone has produced so far, not because it settles the question.

The load-bearing control is believed to be the **effort tier**, not the
prompt. This repo uses **Medium** for routine Sol work. That is a settled
convention, not a measured result: no effort-tier comparison has been run, and
the relative effectiveness of tier versus prompt rules is unmeasured.

**Integrity flag.** METR recorded the highest detected cheating rate of any
public model it has evaluated for Sol, including exploiting bugs in the eval
harness itself. Never accept Sol's green test results at face value. Verify
independently. This applies to Sol acting as a reviewer as well as Sol acting
as an implementer.

## Where this repo stands

Measured on this branch after `session-logs` dropped its optional-session-log mention from `knowledge-persistence`. Two numbers, and they are not interchangeable. The
**always-on corpus is 7 rules, 70,469 bytes**: the ones that load regardless
of what you touch. The **effective context on a `.py` edit is 98,398 bytes
across 11 files**, which is the always-on corpus plus the path-scoped rules
that a Python file activates. Use the first when arguing about what every
session pays. Use the second when arguing about what a specific edit pays.

Regenerate both with the repo's own gate, which is the authority these
figures come from:

```bash
uv run --frozen python scripts/validation/instruction_budget.py --format table
```

**State the basis whenever you quote a number.** That command measures the
generated `.github/instructions/` mirrors. The `.claude/rules/` sources are
116 bytes larger in total (70,585 always-on) because `generate_rules.py`
strips the `priority:` frontmatter key that the Copilot tree does not use.
An earlier draft of this document mixed the two bases in one paragraph and
published a corpus size that matched neither. If a figure here disagrees with
the command above by roughly a hundred bytes, that is the reason; if it
disagrees by more, the document is stale and the command wins.

One book rule loads on every file. `pragmatic-programmer.md` was narrowed to
code files in PR #4424, which recovered 11,225 always-on bytes, the largest
single reduction this corpus has taken. What remains always-on is not the
largest rule either: `voice.md` at 18,166 bytes is the single biggest
always-on file.

| Rule | Bytes | Loading | Scenario file | Scored result |
|---|---|---|---|---|
| `code-quality.md` | 14,152 | always-on | 3 positive, 1 negative | none |
| `pragmatic-programmer.md` | 11,375 | code files only | 3 positive, 1 negative | none |
| `unified-software-engineering.md` | 7,469 | code files only | 3 positive, 1 negative | yes |

That leaves 14,152 always-on bytes of book-derived rule, 20.0% of the
70,585-byte always-on corpus measured at source. `code-quality` and
`pragmatic-programmer` had no scenario file at all until PR #4017 added one to
each on 2026-08-03, which is how they grew unchallenged for four months.

A scenario file is not a result. `software_engineering_library_activation_ci.py`
gates only the eight progressively-disclosed books, so nothing scores these
three in CI. They are measurable now, not measured.

**The rule that was measured is not in that corpus.**
`unified-software-engineering.md` declares `paths:` scoped to source files, so
it loads on a code edit and not otherwise. Carrying its result across to the
always-on book rule is an extrapolation, not a measurement. State it that
way whenever the number gets quoted.

Always-on status is declared **three** ways in this tree, which is the trap:

| Form | Rules |
|---|---|
| `applyTo: '**'` | `builder-ethos`, `claude-model-patches`, `search-before-building`, `universal`, `voice` |
| `alwaysApply: true` | `code-quality` |
| `paths: ["**"]` | `knowledge-persistence` |

A survey that greps one convention misses the others. The first audit of this
corpus grepped two and reported 8 of the 9 that were always-on at the time;
`knowledge-persistence.md` loads on every file and was absent from the count
for a full review cycle. Enumerate by parsing frontmatter, never by grep.

Parse the **generated** mirrors, not the `.claude/rules/` sources.
`generate_rules.py` drops `alwaysApply:`, renames `paths:` to `applyTo:`, and
synthesizes `applyTo: "**"` for a rule that declares no scope at all or whose
globs are all filtered out as internal-only. Neither of those reaches the corpus
through a source line a grep could find, so the mirror is the authority for
membership even though the source is the authority for content.

Name the tree with the number, because the two mirror trees used to disagree.
`templates/platforms/copilot-cli.yaml:39-40` lists `.github/instructions` under
`keepInternalGlobsFor`, so the internal-glob filter is disabled there and the
internal-only fallback cannot fire. It fires only for the plugin tree, and
before issue #4317 it fired the wrong way: dropping an internal glob left the
rule with no scope at all, and the empty scope defaulted to `**`. Four rules
scoped here to `.agents/` and `.serena/` paths (`governance`, `push-lock`,
`secret-redaction`, and `session-logs`) therefore shipped to every plugin
consumer as always-on, at 11,924 bytes a turn, pointed at directories the
installing repository does not have. Narrow at source, universal in the
product, which is the worst direction for a scope error to fail.

The generator now skips an all-internal rule for any tree outside
`keepInternalGlobsFor` and prunes the artifact it previously emitted, so
`src/copilot-cli/instructions` carries 7 rules and 70,469 bytes, matching
`.github/instructions` exactly. Every figure in this document is now both
numbers. That convergence is the invariant worth guarding: a future remap that
re-widens an internal glob would show up here as the plugin tree growing past
the repository tree, so
`tests/validation/test_always_on_corpus_claims.py` pins the two together rather
than pinning the gap that used to separate them.

They are fenced. The `software-engineering-library` skill contains an explicit
design sentence saying these baseline rules stay loaded while the other eight
books moved to progressive disclosure under ADR-088. Do not cut them without
updating that sentence in the same change.

**The cut is not currently justified by evidence.** See
`rule-audit-procedure.md` for what the eval can and cannot resolve.

## The 8KB story, so nobody re-investigates

`AGENTS.md` carried a `<8KB` context budget line for months with no source.
It was real. Commit `77edc827` (PR #1022, 2026-01-31) adopted the Vercel
strategy and wrote "Total passive context: ~4.5KB (well under Vercel's 8KB
threshold)".

The always-on corpus is 8.6x that threshold and a Python edit sees 12.1x,
measured at source. The enforced budget ceiling in
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

<!-- vendor-portability: declared, mixed kinds. Two paths are citations (AGENTS.md, scripts/validation/instruction_budget_constants.py), named as historical provenance for the 8KB budget figure so a future reader does not re-investigate a settled question. One is not: the command under "Measuring the corpus" invokes scripts/validation/instruction_budget.py, and scripts/ ships in no plugin root, so that command cannot run in a vendored install. The surrounding doctrine still applies without it; only the local re-measurement is lost. SKILL.md labels the routing trigger contributor-only because this file and rule-audit-procedure.md both assume a full checkout. Two more are citations added for the two-tree divergence: templates/platforms/copilot-cli.yaml is the generator config whose keepInternalGlobsFor line is the sole cause of the divergence, and the .agents/ reference names the very paths a vendored install lacks, which is the point of that sentence. Neither is executable; both are provenance a reader would otherwise have to re-derive. Issue #2050. -->
