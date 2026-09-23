# Model Context Doctrine

Current as of 2026-09-22. Covers Claude Opus 5, GPT-5.6 Sol/Terra/Luna,
and GPT-6 Astra/Sol/Luna.

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

Anthropic removed much of Claude Code's system prompt for Opus 5 without
degrading coding evals. The named failure mode is **overconstraint**:
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

- "Keep CLAUDE.md concise"
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

Vercel measured stronger results for always-on passive context than for skills.
Read plainly, that says put everything always-on. This repo read it that way.
PR #4424 and the `lsp-first` rescope narrowed rules. Issue #4871 moved
`code-quality` and `pragmatic-programmer` to code files after finding scope
keys that Claude Code ignores. Issue #5492 narrowed `knowledge-persistence` to
the trees it governs. Issue #5404 later grew `builder-ethos` and `voice`.

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

Using the Vercel result to justify always-on generic engineering content is a
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

Test 1 has a trap, and this repo walked into it from the other side. Repeated
evals on `unified-software-engineering.md` found that the **full rule body
beat baseline while its description alone did not**. See
`rule-audit-procedure.md` for the procedure and caveats.

Under a naive reading of test 1 this rule should have been cut. It is
synthesized from Clean Code, Pragmatic Programmer, and SOLID, all of which the
model has read. **The available result does not license cutting it.** The
direction is consistent across independent runs, but the gaps do not all clear
the noise floor. Read that as: the conservative policy blocks the cut, not as
proof the body earns its slot. Two caveats on the models: attribution rests on
run filenames rather than anything the artifact records (issue #3956), and the
provider supplies rule text as a user message, so this measures priming, not
the loading path production uses.

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

**How far this generalizes is not yet measured.** The evidence covers one rule.
The direction is consistent and the mechanism is plausible, but that evidence
cannot establish that arbitration always earns a slot. Treat this as a reason
to measure a rule before cutting it, not as a standing exemption for anything
that calls itself a tiebreaker.

This is a refinement of Shihipar, not a refutation. Anthropic cut restated
constraint. It did not claim that policy about which constraint wins is free
to cut.

## Per-model levers

Two axes, and conflating them is the mistake this section exists to prevent.

**Generation** (`gpt-5.6`, `gpt-6`) sets the API contract: which parameters the
endpoint rejects. That is code, not doctrine, and it belongs in
`_REASONING_MODEL_RE` in `scripts/eval/_providers.py`, which matches by id
prefix so one alternation covers every tier in a generation at once.

**Tier** (Sol, Terra, Luna, Astra) sets behavior and cost. OpenAI's scheme is
that the number identifies a generation while the names "identify durable
capability tiers that can advance on their own cadence". Sol is the
hard-problem tier, Terra the high-volume tier, Luna the cheap everyday tier.
GPT-6 also offers Sol and Luna. Route them by task shape and an external acceptance check, as the orchestrator policy specifies.

Behavior transfers across neither axis. Do not assume a fix for one model
moves another, and do not write a rule file per tier: rule frontmatter scopes
by `paths:` alone (`scripts/validation/check_rule_scope_keys.py`), so it cannot
branch on the runtime model. A per-tier rule file would load in every session
regardless of model. Per-tier findings go here, in a reference this skill loads
on demand.

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

### GPT-6 Astra

Vendor-documented, not measured here. No audit from `rule-audit-procedure.md`
has been run against Astra; everything below comes from OpenAI's migration
guide dated 2026-09-03 and is recorded so nobody re-reads the guide to find it.
Step 5 of the update procedure blocks changing always-on content on an
unaudited model, and nothing here changes always-on content. Downgrade any
claim the first audit contradicts.

**The lever is believed to be the prompt.** Opus responds to prompt size, Sol
to effort tier. OpenAI documents Astra as responding to explicit instruction
about when to stop and ask. That is a third lever and it is unverified here.

**It pauses for confirmation where other tiers proceed.** The vendor remedy is
narrower than the secondhand summaries of it: "Before asking the user
clarifying questions, you should complete the work that is already authorized
from context and necessary to make the proposed action concrete and
reviewable." That is finish-the-authorized-work-before-asking, not ask-less.
This repo already says it in `AGENTS.md` ("Internal+reversible: act|
External/irreversible: confirm|Ambiguous: act minimal, flag rest") and in
`voice.md` ("act minimally, flag what you assumed"). Astra needs the existing
rule, not a new one.

**Reasoning effort.** The guide maps `none` and `minimal` to `low`; other
settings carry over. This repo passes effort only to `codex exec` in
`docs/eval/scripts/evalkit.py` as a caller-supplied value, so there is no
hardcoded `none` or `minimal` to migrate.

**Formatting.** The guide recommends "clear, concise paragraphs" over
list-by-default. `voice.md` already binds every model in this repo and is
stricter. No Astra-specific text.

### Precedence is not a per-model lever

Astra ships with a documented default that contradicts this repo: "The user's
instructions take precedence over guidelines provided in a skill."

That default is written for skills that are style guidance. Several skills here
are not: `pre_pr.py`, the security scan, and the `/ship` review gate block, and
`AGENTS.md` lists Architecture, New ADRs, Breaking, and Security as Ask First.
The former `claude-model-patches.md` rule, now the ADR-108 partial `templates/skills/partials/claude-model-patches.mustache` rendered into the build, test, plan, and ship skills, resolves this by making model-level nudges
"subordinate to skill workflows, STOP points and confirmation gates".

Resolve it once, for every model, in that precedence stack. Do not restate it
per tier: N tiers means N chances for the copies to drift, and the copy a
session happens to load would decide whether a gate holds. A model whose vendor
default disagrees is a reason to state the repo stack where that model reads
it, not a reason to fork the stack.

## Where this repo stands

Issue #4871 moved `code-quality` and `pragmatic-programmer` to code files.
Issue #5492 narrowed `knowledge-persistence` out of the always-on set.
PR #5498 reduced `voice`.
Issue #5404 added completion guidance to `builder-ethos` and `voice`.
Epic #5456 M4 moved model patches and search guidance into skills.
It also moved much of `voice` into skills with narrower activation.

The generated instruction trees preserve the difference between always-on and
path-scoped rules. Use the generated mirrors to answer membership questions.
Use the source rules to answer content questions.

No book rule loads on every file now. `pragmatic-programmer.md` and
`code-quality.md` load on code files. `unified-software-engineering.md` also
loads on source files. Their scenario files do not prove scored results.
Check `evals/reports/` before moving any rule based on an evaluation claim.

Always-on status uses the supported scope form in this tree:

| Form | Rules |
|---|---|
| `applyTo: '**'` | none today |
| `alwaysApply: true` | none today |
| `paths: ["**"]` | `builder-ethos`, `universal`, `voice` |

Legacy scope forms caused the earlier drift. Claude Code honors `paths:` and
ignores `applyTo:`, `globs:`, and `alwaysApply:`. The generator remaps,
preserves, or drops those forms according to its contract. Do not describe
them as one defect. Issue #4871 records the earlier scope failure.
`scripts/validation/check_rule_scope_keys.py` now fails on any scope key but
`paths:`. Enumerate by parsing frontmatter, never by grep.

Parse the **generated** mirrors, not the `.claude/rules/` sources.
`generate_rules.py` drops `alwaysApply:`, renames `paths:` to `applyTo:`, and
synthesizes `applyTo: "**"` for a rule that declares no scope at all. A rule
whose globs are all filtered out as internal-only takes the opposite path: the
generator skips it entirely rather than universalizing it
(`build/scripts/generate_rules.py:349-350`, issue #4317). Neither outcome
reaches the corpus through a source line a grep could find, so the mirror is
the authority for membership even though the source is the authority for
content.

`templates/platforms/copilot-cli.yaml:39-40` lists `.github/instructions` under
`keepInternalGlobsFor`, so the internal-glob filter is disabled there and the
internal-only fallback cannot fire. It fires only for the plugin tree, and
before issue #4317 it fired the wrong way: dropping an internal glob left the
rule with no scope at all, and the empty scope defaulted to `**`. Internal
rules then shipped as always-on in plugin consumers, even when those consumers
did not have the referenced directories. Narrow at source, universal in the
product, which is the worst direction for a scope error to fail.

The generator now skips an all-internal rule for any tree outside
`keepInternalGlobsFor` and prunes the artifact it previously emitted, so
`src/copilot-cli/instructions` preserves the supported membership and skips
internal-only rules. A future remap that widens an internal glob must not add
that rule to the plugin tree, so
`tests/validation/test_always_on_corpus_claims.py` checks membership directly.

They are fenced. The `software-engineering-library` skill contains an explicit
design sentence saying which of these baseline rules load on every turn and
which load on code files, while the remaining books moved to progressive
disclosure under ADR-088. Do not rescope or cut them without updating that
sentence in the same change.

**The cut is not currently justified by evidence.** See
`rule-audit-procedure.md` for what the eval can and cannot resolve.

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
6. Update the per-model section, the activation guidance, and the date at the
   top of this file.

## Sources

| Source | Date | Type |
|---|---|---|
| Anthropic, Context Engineering for Claude 5 | 2026-07-24 | Vendor, first party |
| Vercel passive context vs skills | 2026-02-08 | Third party, reproduced locally |
| METR evaluation of GPT-5.6 Sol | 2026 | Third party |
| OpenAI, GPT-6 Astra migration guide | 2026-09-03 | Vendor, first party |
| OpenAI, GPT-5.6 Sol/Terra/Luna tier naming | 2026-07-09 | Vendor, first party |
| PR #1022, commit `77edc827` | 2026-01-31 | This repo |
| ADR-088 | see `.agents/architecture/` | This repo |

<!-- vendor-portability: declared. The cited repository paths provide provenance
for the activation and generation claims above:
.agents/analysis/vercel-passive-context-vs-skills-research.md,
.agents/architecture, build/scripts/generate_rules.py,
docs/eval/scripts/evalkit.py, scripts/eval/_providers.py,
scripts/validation/check_rule_scope_keys.py, and
templates/platforms/copilot-cli.yaml. The routing trigger remains
contributor-only because this file and rule-audit-procedure.md assume a full
checkout. Issue #2050. -->
