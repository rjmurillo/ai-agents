# Rule Audit Procedure

<!-- vendor-portability: contributor-facing reference for the rjmurillo/ai-agents
     repository itself; intentionally references upstream-only eval scripts
     because repo contributors run the rule audit there (issue #2050) -->
<!-- # taste-lint: ignore file-size -->
<!-- file-size rationale: this is one linear procedure, executed top to bottom
from step 0 through step 8. The 500-line limit encodes code cohesion, and the
linter's own remediation advice for it (extract helper functions, type
definitions, constants) has no referent in a prose procedure. Splitting the
steps across files breaks the execution path a reader follows. Same treatment
as the peer reference doc `memory-search/references/memory-router.md` and the
over-limit prose ADRs cited in ADR-085. -->

How to decide whether an always-on rule earns its slot, with evidence rather
than taste. Companion to `model-context-doctrine.md`, which holds the argument
this procedure tests.

Run this when a new model ships, when a harness updates, or when someone
proposes adding or cutting always-on content.

## Read this first

The instrument has known limits. Skipping to the numbers without reading
"What the instrument can and cannot resolve" below has already produced one
wrong conclusion on this branch.

## Step 0a. Pre-register the decision rule before any scored eval run

This step is BLOCKING. A decision rule chosen after seeing the data it grades
is exploratory analysis, not a reproducible audit. The sign-counting rule
(issue #3957) was selected retroactively, which invalidates the p-value it
produced and makes any conclusion from those runs non-reproducible.

Before running `eval-rule-activation.py` for a new rule audit:

1. Write down the decision rule in plain text. Example: "I will accept a
   progressive-disclosure recommendation if and only if `description` ties or
   beats `full` consistently, with no material degradation."
2. Commit that text to a file or to the issue body BEFORE running any eval.
   A commit timestamp before the first eval run is the evidence. A comment
   added after seeing results is not pre-registration.
3. Record what would falsify the recommendation. If no outcome would change
   your conclusion, the eval is not providing evidence.

Violating this step means the audit produced an exploratory finding, not a
decision. Label it as such. Do not act on an exploratory finding as though it
were a reproducible result.

## Step 0. Deterministic baseline

Read the generated `.github/instructions/` mirrors before touching a model.
Parse their frontmatter to find the always-on rules.

The mirrors answer membership questions. The canonical `.claude/rules/` files
answer content questions. Refresh the mirrors after editing a source rule.

## Step 0b. Conflict audit

Run this before touching a model. A contradiction between
two always-on files is the highest-value thing you can remove: it costs tokens
twice and it also makes the model guess, so fixing one buys budget and behavior
at the same time.

**Read the files. Do not build a scanner.** Automated conflict detection was
tried and disproved on 2026-08-01. An opposite-polarity bag-of-words scanner
produced many false candidates. Manual review found agreement or duplication,
such as "Pin Actions to SHA" restated across the corpus, while the known true
conflict shared less vocabulary than ordinary agreement. Signal and noise are
inverted with respect to shared-vocabulary ranking, so the instrument is
structurally incapable of the job. Rebuilding it with better tokenization or a
higher threshold does not help; the ordering is backwards, not noisy.

**What a real conflict looks like.** Contradictions hide in the verb, not the
vocabulary. The one found in this corpus:

| Source | Scope | Said, before the fix |
|--------|-------|------|
| `AGENTS.md` | entrypoint, read first | `Use bash` under **Never**, removed by #4169 |
| `.claude/rules/universal.md` | applyTo `**` | MUST NOT **create** new bash scripts |
| `.claude/rules/ci-scripts.md` | scripts and build paths | MUST NOT **create** new `*.sh` scripts |
| `.claude/rules/claude-model-patches.md` (retired 2026-09-12 into `templates/skills/partials/claude-model-patches.mustache`) | applyTo `**` at the time | publishes an **allowed** bash list |

Both rules that state the prohibition say *create*. The compressed index said
*use*. Nothing
reconciled them, so an agent reading the entrypoint first would refuse `git`
and `gh`. Compression is where this defect class is born: when a long rule is
squeezed into an index line, the verb is the first casualty.

**Two hypotheses that were checked and are false.** Do not re-file these.

- `code-quality.md` versus `pragmatic-programmer.md` on naming, error handling,
  and testing is **complementary altitude**, not contradiction. One is
  mechanical and language-specific (`try`/`finally`, `raise`), the other is
  architectural (detect close to the source, separate retryable from
  permanent).
- `universal.md` SHOULD use Python versus `ci-scripts.md` MUST be Python is
  **scope graduation**, the normal RFC 2119 shape of a broad SHOULD tightening
  to a MUST in a narrower path.

**Procedure.** List the always-on set from Step 0. Read each file's directive
lines. For every rule that appears in more than one file, compare the verb and
the scope, not the topic. A narrower scope being stricter is correct. The same
scope disagreeing on the verb is the defect. File one issue per contradiction
with all sources quoted, because the fix is a wording decision and needs a
record.

## Step 1. Behavioral baseline

Use the Copilot CLI provider. It reaches the models this repo actually ships
against and costs credits rather than API spend.

```bash
EVAL_PROVIDER=copilot-cli uv run python scripts/eval/eval-rule-activation.py \
  --scenarios tests/evals/rule-scenarios/<rule>.json \
  --model claude-opus-5 \
  --output /tmp/audit/opus-1.json
```

Repeat with `--model gpt-5.6-sol`. Run both, always. They disagree, and the
disagreement is the point.

Three mechanisms run per scenario:

| Mechanism | Treatment text | Answers |
|---|---|---|
| `baseline` | none | What does the model do unprompted? |
| `description` | frontmatter only | Does the routing line alone suffice? |
| `full` | whole rule body | Does the body add anything? |

**Where the treatment text goes depends on the provider, and it is not always
a system prompt.** The Anthropic API provider sets it as the system prompt.
The Copilot CLI provider has no separate system channel, so it prepends the
treatment to the user message. That measures priming, which is a weaker
analogue of the loading path production uses. Do not describe a Copilot CLI
result as a system-prompt result.

**The comparison that decides the question is `description` against `full`.**
If they tie, the body earned nothing measurable and is a candidate for
progressive disclosure. Read the decision rule below before acting on a tie:
a single tie is not evidence, and the cut requires replicated absence of
degradation, not a single equality. `baseline` tells you whether the rule was
ever needed at all.

### Ambient instructions contaminated runs archived before 2026-07-29

The provider sandboxes `cwd` so repo instruction files cannot leak into the
control cell, and passes `--no-custom-instructions` so user-level ones in
`~/.copilot/` cannot either. The second flag was added on 2026-07-29. Every
run archived before that carries ambient user-level instructions in all three
cells.

Do not compare prompt usage between archived runs and controlled runs. The
provider now disables repository and user-level instructions for the control
cell. Older runs used a different ambient condition, so treat them as a
separate record rather than estimating a footprint change from provider output.

**The direction of that bias is unknown.** It is tempting to argue the ambient
block only adds a constant to every cell and so compresses deltas toward zero,
which would make the archived deltas lower bounds. That does not follow.
Ambient text that overlaps the rule body could substitute for it and shrink
the gap, or prime the behavior the rule asks for and widen it; position and
salience effects cut either way. Treat pre-2026-07-29 deltas as measured under
a different and less controlled condition, not as conservative estimates.
Settling the direction needs a two-by-two: ambient on and off crossed with
`description` and `full`.

## Step 2. Read the table honestly

Check in this order:

1. **`gating_judge_failures` must be empty.** A gating failure means a cell
   the verdict rests on went ungraded, and the verdict says
   `FAIL_JUDGE_ERRORS`. `total_judge_failures` may exceed it, counting `full`
   on a routed target and `baseline` on the negative pool, neither of which
   gates anything. The table names the excluded cells when the counts differ.
2. **The negative case should be high on every mechanism the target can reach.**
   Checked before coverage: an observed harm outranks an unproven benefit. A
   drop means the rule fires on work it should ignore, whatever the positive
   scores say. For a skill reference the gate reads `description` only: `full`
   force-injects the reference routing exists to keep out.
3. **Every graded cell must be complete.** An off-rubric cell is unmeasured,
   so it leaves the average without raising `judge_failed`. Each pool is gated on the
   mechanisms its verdict names: the negative pool on what the target can
   reach, the positive pool on `baseline` and `description` only, never `full`.
4. **Only then read the deltas**, against the noise floor below.

## What the instrument can and cannot resolve

**Read this before believing any number the eval prints.** Repeated scoring of
identical rule text showed material judge variance. A single run cannot resolve
a small effect. Never cut or keep content on one run.

The eval path is single-shot against an LLM judge. Treat direction as evidence
only when it survives the registered repeat policy, and treat magnitude as
context rather than a decision rule. Do not copy a result snapshot into this
procedure. Keep raw artifacts and reproduce the result from the current tree.

### Read direction, not magnitude

Means can be swamped while direction remains useful. Compare `full` with
`description`, not either arm with an unrelated baseline. Record ties and read
the result with the preregistered two-tailed rule. A large delta in one run is
not evidence by itself.

#### Registered decision rule, 2026-08-03

Fixed here before the next audit runs, which makes that audit this rule's first
confirmatory test (issue #3957). Editing any line below after seeing a run
makes that run exploratory too, so change it before, or not at all.

- **Run policy.** Use the fixed repeat design across both model families. Each
  non-tied run contributes one sign. Do not add runs because the result is
  close, and discard a run only for a recorded provider error, never for its
  result.
- **The unit.** A run contributes the direction of its delta between the two
  arms being compared. Magnitudes are recorded and do not vote.
- **Ties.** An exact tie contributes no sign. That is the sign test's own
  convention.
- **Tails.** Two-tailed, always. A direction is declared before the run and is
  not rescored one-tailed afterwards. Do not choose the tail after seeing the
  result.
- **Threshold for an addition or a keep.** Apply the registered sign-test
  threshold. Outcomes below that threshold do not decide. A later audit starts
  the same fixed design from zero.
- **Threshold for a cut.** A cut fails when the pre-cut version wins the sign
  count at that threshold, and passes otherwise. This accepts a null and
  cannot separate "no degradation" from "too little evidence". The fixed
  design keeps that blind spot the same in every audit.

The historical audit remains exploratory because the decision rule was written
after its runs. Do not treat its direction as a current pass or as a permanent
measurement.

### Scoring contract

The judge returns the required score fields for each sample. Reduce each field
within a cell using the registered reduction, then derive the mechanism result
from the scenario set. Preserve incomplete or malformed cells as unmeasured.
Never replace missing observations with zeros or inferred values.

The old audit used a reduction that could produce a score the judge never
returned. The current writer records the reduction explicitly, rejects missing
or off-rubric cells, and keeps negative scenarios in the gate. Do not copy old
snapshots into this procedure.

### Archive and provenance

Some archived judge output required recovery. The recovery exposed parser
ambiguity, incomplete provenance, and a circular attribution check. Read
`rule-audit-evidence.md` before relying on any archived result. The parser
defects and their fixes are in `rule-audit-parser-forensics.md`.

**Provenance is recorded by hand because the artifacts do not carry it
(issue #3956).**

| Field | Value |
|---|---|
| Artifacts | `fx-opus5`, `var-opus-{1,2,3}`, `t-sol56`, `var-sol-{1,2,3}` |
| Rule under test | `unified-software-engineering` |
| Provider | `EVAL_PROVIDER=copilot-cli` |
| Requested models | `claude-opus-5`, `gpt-5.6-sol` (actual model not recorded) |
| Judge samples | Median reduced per cell |
| Generations | Fixed per cell |
| Ambient instructions | present; these runs predate `--no-custom-instructions` |
| Harness state | postdates the 2026-07-29 fix for silently zero-scored cells |
| Date | 2026-07-29 |

The harness row matters. An earlier defect scored a cell zero when the
provider call failed, which pulls an average down without leaving a mark. Do
not pool artifacts from before that fix with newer artifacts.

Model attribution rests on the filenames above and nothing else. The artifacts
are committed at
`.project-toolkit/analysis/eval-artifacts/2026-07-29-unified-software-engineering/`.

Other limits, all real:

- **The sign-counting rule was chosen after seeing these runs.** It is the
  reading that survived the noise, not a rule fixed in advance. The rule is
  now registered above and dated 2026-08-03, which makes the first audit run
  after that date its first confirmatory test (issue #3957). The earlier runs
  stay exploratory whatever that audit returns.
- **The judge is the same model family being evaluated.** A known validity
  weakness, not a settled one.
- **Per-cell scores use a median reduction.** That smooths judge noise, not
  model noise. Model noise needs repeat runs.
- **Runs carry no provenance.** Artifacts record only `rules`: no provider,
  model, commit, or CLI version, so attribution rests on the filename. Record
  them by hand until that is fixed (issue #3956).
- **The Copilot provider does not test passive context.** Copilot CLI has no
  separate system channel, so `_CopilotCLIProvider` folds the treatment into
  the user prompt (`scripts/eval/_copilot_cli.py`). A `copilot-cli` result
  measures user-message priming. Whether it transfers to always-on placement
  is an assumption, not a measurement (issue #3934).
- **Negative scenarios could not fail a rule until #3933.** `aggregate` now
  returns `FAIL_OVER_ACTIVATION` below `MIN_RESTRAINT_SCORE`, and
  `FAIL_NEGATIVE_INCOMPLETE` or `FAIL_POSITIVE_INCOMPLETE` when a gating pool
  was not fully graded. Harm outranks coverage, and an unproven harm outranks
  an unproven benefit. **The gate is
  vacuous here**: the historical suite did not exercise a failing negative
  outcome. Unit tests exercise it; the historical suite cannot.

## Step 3. Decide

| Evidence | Action |
|---|---|
| `description` ties or beats `full`, replicated across runs, with no replicated degradation | Move the body to progressive disclosure |
| `full` beats `description` by more than the noise floor, replicated | Keep the body, record the result |
| Delta under the noise floor on a single run | **Not resolved.** Do not cut. Say so plainly |
| No scenario file exists | **Cannot be gated.** Write scenarios first |

A tie belongs in the third row, not the first. Replication is what separates
the rows: an isolated run cannot distinguish a real equivalence from noise, and
the noise floor here spans most of the usable range.

The last row is the common case and the easy one to skip. As of 2026-09-02,
`code-quality.md` has a scenario file from PR #4017, but no scored result in
`evals/reports/`. No **book-derived** rule is always-on now. Issue #4871 found
`code-quality` scoped with `alwaysApply:`, a key Claude Code ignores, and
rescoped it to code files. Epic #5456 M4 later moved most of `voice` into the
spec, plan, review, and autoplan skills. PR #4424 narrowed
`pragmatic-programmer` to source files, but it used `applyTo:` until issue
#4871 moved the scope to `paths:`.

Written scenarios are not the missing piece for either rule. A scored run is.
`check_rule_activation_coverage.py` lists both as uncovered and still exits 0,
because the uncovered set is inside its recorded baseline. Nothing goes red
while the gap stays open, which is why reading the scenario directory is a
worse signal than reading `evals/reports/`.

Always-on status uses the supported `paths:` form. The legacy `applyTo:` and
`alwaysApply:` forms fail the scope-key check. The supported form can use a
block list or the inline `paths: ["**"]` shape. Both shapes matter to a survey:
a regex written for the inline form misses the block list. That is how an
earlier draft got the ranking wrong. Enumerate by parsing frontmatter.

Applying the doctrine to **authoring guidance** is a separate decision from
**cutting existing content**. The first is an argument about where new content
should go. The second changes model behavior and needs an eval.

## Step 4. Prove the delta

After any change to always-on content:

1. `uv run python build/scripts/generate_rules.py` to refresh the mirrors.
2. Re-read Step 0 and check the membership.
3. Repeat Step 1 across the registered models and apply the test that
   matches the direction of the change. Both thresholds are fixed by the
   registered decision rule in Step 3; read them there rather than deciding
   here. **A cut and an addition have opposite success conditions.** For a cut,
   success is the absence of replicated degradation: the sign result must not
   favor the pre-cut version. Demanding that a cut clear the noise floor is
   incoherent, because a good cut leaves the delta near zero. For an addition or
   a keep decision, success is replicated improvement whose sign count reaches
   the registered threshold. Magnitudes are recorded and do not vote.
4. If the rule is fenced, update the fence in the same commit. The
   `software-engineering-library` skill currently fences the book rules.

## Step 5. Adversarial review

Run a review with the model that did not produce the change. Sol reviewing
Claude's work and the reverse both surface things a single model misses.

Give the reviewer the claim, the evidence, and explicit permission to reject
it. A prompt that asks "review this" gets agreement. The working shape:

- State what the branch claims, including the reasoning, not just the diff.
- Name the specific arguments to attack, one per section.
- Include the evidence and ask whether it supports the conclusion.
- Require `file:line` citations and ban style commentary.
- Say "if a section has no defect, say so in one line, do not manufacture
  findings". Without this the reviewer pads.
- End with the single most important question, stated as a yes or no.

A full worked example is in this repo's history: the adversarial prompt used
for the Shihipar audit, session `2026-07-29-session-3876`.

**When Sol is the reviewer, verify anything it reports as passing.** See the
METR integrity flag in `model-context-doctrine.md`.

## Known instrument gotchas

These each cost real time. Some are fixed; the ones carrying an open issue
number are not. The shapes recur either way.

- **Judge failures used to score as zero.** An unparseable sample could zero a
  whole cell, and zeroed cells were averaged into the mechanism mean. Because
  failures are not evenly distributed across mechanisms, this could invert the
  ranking. Fixed on 2026-07-29. Older result files with
  `total_judge_failures` may carry a biased table.
- **A fence width was misread and refused.** The fence matcher assumed a
  narrower run, so a legal payload with a wider fence closed at an inner run
  and yielded a truncated body that would not parse. The sample was dropped.
  Recorded rather than fixed at
  first, on the reasoning that widening the matcher would re-introduce the
  candidate selection the exactly-one-fence rule exists to remove. **That
  reasoning was wrong**: pairing the close to the width of the run that opened
  it collects every block exactly as before and still refuses anything other
  than one, so no selection returns. Fixed on 2026-07-30, archive unaffected.
- **A lone fence outranked an unfenced verdict beside it.** Requiring exactly
  one fenced block removed the choice among fences and left the choice between
  the fence and the prose around it. A judge that wrote its verdict as
  unfenced text and fenced a rubric exemplar it had labelled "do not use" was
  answered with the exemplar, which then parsed cleanly and was published as a
  recovered sample. Unwrapping now also requires that nothing but whitespace
  sit outside the fence: that is the only condition under which unwrapping is
  a rewrite of the payload rather than a choice within it. Found by
  adversarial review, fixed on 2026-07-30. The archive is unaffected,
  and recovery preserves every archived request, response, and verdict
  byte-for-byte.
- **A clean parse was treated as proof of a single answer.** Adversarial review
  attacked recovery and left the strict parse alone, on the reasoning that a
  payload which parses whole cannot be ambiguous. JSON nests, so it can: a
  second verdict sits inside the first as a member, a list element, or a
  quoted string, and the grammar is satisfied. Duplicate-key rejection does
  not see these, because a nested key is not a repeated one. The guard that
  refuses exactly this already existed in recovery but not in the strict path,
  so the miss was a path that did not know it needed a check rather than a
  missing check. It now runs before any parse. Found by adversarial review,
  fixed on 2026-07-30. **Its cost
  against the published table is recorded in the full archive, not argued
  from failures alone**: `recovered-judge-payloads.json` holds the original
  success and failure payloads, so the success path can be replayed. Issue
  #3998 was filed when the archive was believed to keep raw only for failures;
  it does not apply to this run.
- **Agentic CLI output is not clean JSON.** The provider reads
  `~/.copilot/session-state/<uuid>/events.jsonl` and correlates by the sandbox
  working directory, which is race-free. Falling back to stdout parsing mixes
  tool traces into the answer. That fallback also fires on a filesystem error,
  silently skipping the only check that confirms which model actually served
  the request, so a run can be attributed to the wrong model with no warning
  (issue #3959).
- **The Copilot CLI stdout usage metadata is non-monotonic.** Do not use it as
  evidence. The event log is the authoritative source for provider state, and
  `session.usage_checkpoint` is the value of `type`, not a nested key.
- **The CLI loads `AGENTS.md` from its working directory.** Eval calls must run
  in an empty temp directory or the repo's own instructions contaminate the
  baseline mechanism. User-level instructions in `~/.copilot/` ignore the
  working directory entirely and need `--no-custom-instructions`. Runs archived
  before 2026-07-29 predate that flag; see Step 1 for what that means for them.
- **Most eval entry points still demand `ANTHROPIC_API_KEY`** even when
  `EVAL_PROVIDER` selects a keyless provider. Tracked in issue #3924.
  `eval-rule-activation.py` is fixed and shows the pattern.
- **The archive nests dicts where a walker expects lists.** `rules` is a dict
  keyed by rule name, and each scenario's `mechanisms` is a dict keyed by
  `baseline`/`description`/`full`. Only `scenarios` is a list. A walker that
  assumes lists finds zero samples and prints a clean result from no data,
  which is the same failure class as the parser defects in the evidence
  document: a confident answer derived from nothing. Reading
  `rules[<name>].scenarios[].mechanisms[<mech>].score_samples[]` and
  re-medianing each cell reproduces the published table exactly.
- **Recovering discarded samples.** Failed samples store the truncated raw
  payload in `reasoning` behind a `judge parse error:` prefix; strip it and
  feed the remainder to `_salvage_scores`. Successful samples store no payload
  in the artifact at all. Both are recovered in full in
  `recovered-judge-payloads.json` beside it, keyed by the same coordinates and
  attributed by the input-based oracle rather than by the score.

## Scenario files

Live in `tests/evals/rule-scenarios/`. One JSON file per rule.

Each scenario needs an `input`, an `expected_gate`, and a `desc`. Include at
least one negative case with `expected_gate` set to
`skip-rule-not-applicable`, so the eval can catch a rule that fires on
unrelated work.

Writing scenarios that can actually detect a difference is the hard part. A
scenario the model handles correctly with an empty system prompt proves
nothing about the rule. Aim for cases where the rule's specific guidance
changes the answer.

<!-- vendor-portability: declared. This procedure uses repository-only eval and generation scripts, so vendored installs cannot run it. The full-checkout audience is intentional. Issue #2050. -->
