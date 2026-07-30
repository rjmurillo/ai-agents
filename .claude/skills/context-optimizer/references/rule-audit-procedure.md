# Rule Audit Procedure

How to decide whether an always-on rule earns its slot, with evidence rather
than taste. Companion to `model-context-doctrine.md`, which holds the argument
this procedure tests.

Run this when a new model ships, when a harness updates, or when someone
proposes adding or cutting always-on content.

## Read this first

The instrument has known limits. Skipping to the numbers without reading
"What the instrument can and cannot resolve" below has already produced one
wrong conclusion on this branch.

## Step 0. Deterministic baseline

Free and instant. Always do this before touching a model.

```bash
uv run python scripts/validation/instruction_budget.py --format json
```

Reports bytes per language baseline, which files are always-on, and headroom
against the ceiling.

Two traps:

- The tool reads the **generated mirrors** under `.github/instructions/`, not
  the canonical `.claude/rules/` tree. Run `uv run python
  build/scripts/generate_rules.py` after editing a rule or the number will not
  move.
- The ceilings in `scripts/validation/instruction_budget_constants.py` track
  measured size, not a goal. A PASS means "no growth since the last ceiling
  raise", not "the corpus is small".

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

A rough size check, run from an empty directory against `claude-opus-5` with
the same prompt twice, once with `--no-custom-instructions` and once without,
showed the flag changed reported usage by roughly 13k input tokens on the
CLI's own stdout counter. **That is all it establishes.** The same counter is
listed under instrument gotchas below as non-monotonic and unusable for
measurement, so it cannot support a claim about relative size, and the probe
omitted `--disable-builtin-mcps`, so neither absolute number is the provider's
floor. Read it as confirmation that the flag does something, not as a
quantity. Before comparing ambient size against rule-body size, measure both
from the event log: read `data.totalNanoAiu` on the events whose `type` is
`session.usage_checkpoint` in `~/.copilot/session-state/<uuid>/events.jsonl`,
under the provider's actual argument list. The `session.` prefix is part of
the type string, not a key at the root of the object.

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

```
| Mechanism    | Pos avg | Neg avg | Δ vs baseline | Graded |
|--------------|---------|---------|---------------|--------|
| baseline     |    3.89 |     5.0 |               |    3/3 |
| description  |    3.67 |     5.0 |         -0.22 |    3/3 |
| full         |    4.11 |     5.0 |         +0.22 |    3/3 |
```

Check in this order:

1. **`total_judge_failures` must be 0.** Any non-zero count means some cells
   were not graded. The verdict will say `FAIL_JUDGE_ERRORS`. Fix the failures
   before reading any number in the table.
2. **The `Graded` column must read `n/n` on every row.** A mean over one
   scenario and a mean over three look identical in the average column. They
   are not comparable.
3. **The negative case should be high on every mechanism.** If it drops, the
   rule is firing on work it should ignore, which is a real defect regardless
   of the positive scores.
4. **Only then read the deltas**, against the noise floor below.

## What the instrument can and cannot resolve

**Read this before believing any number the eval prints.**

The repo already knew this before the 2026-07-29 audit re-derived it.
`scripts/eval/README.md` records that scoring identical rule text twice moved
**5 of 24 tasks** across the pass threshold (ADR-087 Open Requirement 6,
issue #3445). The rule path is single-shot against an LLM judge and cannot
average that away.

Measured 2026-07-29 on `unified-software-engineering.json`, eight runs of
identical inputs through `EVAL_PROVIDER=copilot-cli`, four per model. The full
table is below under "The eight runs, for comparison"; it lives in one place
because an earlier draft carried two copies and they drifted apart, which is
how a stale baseline survived two review rounds.

Run-to-run spread on the `full` delta was **1.00 on Opus 5 and 1.11 on
Sol 5.6**. Sol's `full` delta changed sign, -0.33 to +0.78, on identical
inputs. Baseline alone moved 3.22 to 4.11 with nothing changed.

**Practical rule: at 2 to 3 positive scenarios and one generation per cell, a
single run cannot resolve an effect smaller than about 1.0 on a 0-5 scale.**
That is most of the usable range. Never cut or keep content on one run.

An earlier draft of this document put the floor near 0.3, from two runs. Six
more runs widened it more than threefold. Expect the same if you add runs.

### Read direction, not magnitude

The means are swamped. The **sign is not**:

| Mechanism | beats baseline | ties | pooled mean delta |
|---|---|---|---|
| `description` only | 1 of 8 runs | 3 | -0.14 |
| `full` body | **7 of 8 runs** | 0 | **+0.67** |

The contrast Step 3 actually decides on is `full` against `description`, not
either against baseline. It gives the same answer: `full` wins **7 of 8**, with
per-run deltas 0.44, 0.89, 1.22, 1.22, -0.22, 0.89, 0.78, 1.22. Only three of
those clear the ~1.0 noise floor on magnitude, which is why the decision rests
on the sign count rather than the size of any one delta.

Seven of eight in one direction is p about 0.070 two-tailed under a fair-coin
null. **Read it two-tailed.** The doctrine predicted the opposite direction,
so scoring the one-tailed 0.035 against the result actually observed would be
picking the tail after seeing the data. At 0.070 this is suggestive, not
conclusive, and it is the strongest claim the eight runs support.

The signal survives noise the means do not, and its direction is the same in
both model families: `full` wins 4 of 4 on Opus and 3 of 4 on Sol. Note also
that the `description` row hides three exact ties, so its real record is one
win against four losses. A sign test discards ties.

**So run the eval at least four times per model and count signs.** A
consistent direction across runs is evidence. A large delta in one run is not.
This is the reading that survived the noise in the one audit run so far. It
was chosen after seeing those runs, so treat it as the protocol this document
proposes, not as a protocol that has been validated. Pre-register the run
count, the tie handling, and the decision threshold before the next audit
(issue #3957).

### The eight runs, for comparison

Recorded so a later re-run has something to compare against. Scenario is
`unified-software-engineering`, three positive cells plus one negative,
one generation per cell, judge samples medianed. Scores are 0 to 5.

The numbers below are the positive-scenario average, and they only reproduce
if you reduce in this order:

1. The judge returns three fields per sample: `activation_score`,
   `citation_score`, `behavior_score`.
2. Per cell (one scenario x one mechanism), take the **median** across judge
   samples of each field separately. Three medians.
3. The cell score is the **mean of those three medians**.
4. The published figure is the **mean of the three positive-scenario cells**
   for that mechanism. The negative scenario is scored and reported but does
   not gate the verdict, so read its column yourself (issue #3933).

Three positive cells times three fields is nine medians, which is why a full
run lands on a 1/9 grid. 3.89 is 35/9. Reducing in a different order, for
example averaging the three fields before taking the median, gives different
numbers.

**Step 2 is a defect, not a choice, and the numbers below carry it.** Taking
each field's median independently is a coordinate-wise median, and the result
need not be any sample the judge gave. Three samples of 5/5/1, 5/1/5, and
1/5/5 reduce to 5/5/5, a cell of 5.0, when every judge rated the triple at
3.67. Reducing each sample to its own three-score mean first and taking the
median of those scalars gives 3.67. Measured across all 96 archived cells,
**3 diverge**, worst by 0.333 on a cell and 0.111 on a run average:
`t-sol56` S2 description and S3 baseline, and `var-sol-2` S3 full. Recomputed
end to end, the sign count is unchanged at seven positive against one
negative, p = 0.0703, so the conclusion holds; two of the eight rows shift.
Tracked as issue #3989. Do not reproduce this reduction in a new instrument.

| Model | baseline | description | full | delta desc | delta full | discarded samples |
|---|---|---|---|---|---|---|
| Opus 5 | 3.89 | 3.67 | 4.11 | -0.22 | +0.22 | 6 |
| Opus 5 | 3.67 | 3.89 | 4.78 | +0.22 | +1.11 | 8 |
| Opus 5 | 3.67 | 3.67 | 4.89 | 0.00 | +1.22 | 4 |
| Opus 5 | 3.67 | 3.67 | 4.89 | 0.00 | +1.22 | 6 |
| Sol 5.6 | 3.89 | 3.78 | 3.56 | -0.11 | -0.33 | 0 |
| Sol 5.6 | 3.44 | 3.33 | 4.22 | -0.11 | +0.78 | 0 |
| Sol 5.6 | 3.22 | 3.22 | 4.00 | 0.00 | +0.78 | 0 |
| Sol 5.6 | 4.11 | 3.22 | 4.44 | -0.89 | +0.33 | 0 |

### The judge discarded Opus samples unevenly, and it was recoverable

Seventeen of the 48 Opus cells were averaged over one or two judge samples
instead of three, and all 24 lost samples are in the four Opus artifacts.
Recovering them moved one cell (`fx-opus5` baseline, 3.83 to 3.89) and left
the sign count unchanged. The table above is the post-recovery one, so every
published cell uses three samples; seventeen of them get at least one of those
three from post-hoc recovery of a truncated prefix, and seven get two.

The full accounting, the confounds it creates for the table above, and the
seventeen defects found in the verdict-parsing code across fourteen review
rounds are in `rule-audit-evidence.md`. Read it before citing a cell from this
table. One of the seventeen, the most recent, is the first whose cost against
this table could not be measured: the archive keeps raw payloads only for
failed samples, so a defect on the success path leaves no evidence either way
(issue #3998).

**Provenance for the eight runs, recorded by hand because the artifacts do not
carry it (issue #3956).**

| Field | Value |
|---|---|
| Artifacts | `fx-opus5`, `var-opus-{1,2,3}`, `t-sol56`, `var-sol-{1,2,3}` |
| Rule under test | `unified-software-engineering`, 3 positive and 1 negative scenario |
| Provider | `EVAL_PROVIDER=copilot-cli` |
| Requested models | `claude-opus-5`, `gpt-5.6-sol` (actual model not recorded) |
| Judge samples | 3 per cell, median reduced |
| Generations | 1 per cell |
| Ambient instructions | present; these runs predate `--no-custom-instructions` |
| Harness state | postdates the 2026-07-29 fix for silently zero-scored cells |
| Date | 2026-07-29 |

The harness row matters. An earlier defect scored a cell zero when the
provider call failed, which pulls an average down without leaving a mark. All
eight runs above were taken after that was fixed, so no cell in the table is a
disguised provider error. A run recorded before that date is not comparable
and should not be pooled with these.


Model attribution rests on the filenames above and nothing else. The artifacts
are committed at
`.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/`.

Other limits, all real:

- **n is 2 or 3 positive scenarios per rule.** One cell moves the average a
  lot. `unified-software-engineering` has 3; most rule scenario files have 2.
- **The sign-counting rule was chosen after seeing these runs.** It is the
  reading that survived the noise, not a rule fixed in advance, so the p-value
  above is exploratory (issue #3957). Treat the four-runs-per-model protocol as
  a hypothesis this document proposes, and the next audit as its first real
  test.
- **The judge is the same model family being evaluated.** Treat it as a known
  validity weakness, not a settled one.
- **Per-cell scores are a median of 3 judge samples.** That smooths judge
  noise, not model noise. Model noise needs repeat runs.
- **Runs carry no provenance.** Result artifacts record only `rules`. Provider,
  requested and actual model, commit, and CLI version are not stored, so model
  attribution rests on the filename. Record them by hand until that is fixed
  (issue #3956).
- **The Copilot provider does not test passive context.** Copilot CLI has no
  separate system channel, so `_CopilotCLIProvider` folds the treatment into
  the user prompt (`scripts/eval/_copilot_cli.py`). A `copilot-cli` result
  measures user-message priming. Whether it transfers to always-on placement
  is an assumption, not a measurement (issue #3934).
- **Negative scenarios cannot fail a rule.** `aggregate` computes the negative
  average and the verdict never reads it (issue #3933). Over-activation is
  invisible to the verdict.

## Step 3. Decide

| Evidence | Action |
|---|---|
| `description` ties or beats `full`, replicated across runs, with no replicated degradation | Move the body to progressive disclosure |
| `full` beats `description` by more than the noise floor, replicated | Keep the body, record the number |
| Delta under the noise floor on a single run | **Not resolved.** Do not cut. Say so plainly |
| No scenario file exists | **Cannot be gated.** Write scenarios first |

A single tie is the third row, not the first. Replication is what separates
them: one run cannot distinguish a real equivalence from noise, and the noise
floor here spans most of the usable range.

The last row is the common case and the easy one to skip. As of 2026-07-29,
`code-quality.md` (14,152 bytes) and `pragmatic-programmer.md` (12,219 bytes)
have no scenario file at all. They are the two largest **book-derived**
always-on rules, ranks 2 and 3 in the corpus; `voice.md` (19,624 bytes) is
larger than either. They cannot be audited until someone writes scenarios for
them.

Note that always-on status is declared **three** different ways: `applyTo:
'**'` (six rules), `alwaysApply: true` (two), and `paths: ["**"]` (one,
`knowledge-persistence.md`). A survey that greps for one convention misses the
others. That is how an earlier draft got the ranking wrong and then, after a
correction that added only the second form, still reported 8 rules instead of
9. Enumerate by parsing frontmatter.

Nine rules is the corpus. Do not hardcode its size; it changes on every rule
edit. Regenerate it below, and say which basis you mean: this gate reads the
generated `.github/instructions/` mirrors, which total 139 bytes less than the
`.claude/rules/` sources because `generate_rules.py` strips `priority:`.

```bash
uv run --frozen python scripts/validation/instruction_budget.py --format table
```

Applying the doctrine to **authoring guidance** is a separate decision from
**cutting existing content**. The first is an argument about where new content
should go and does not need an eval. The second changes measured behavior and
does.

## Step 4. Prove the delta

After any change to always-on content:

1. `uv run python build/scripts/generate_rules.py` to refresh the mirrors.
2. Re-run Step 0 and record the byte delta.
3. Re-run Step 1 on both models, at least four times per model, and apply the
   test that matches the direction of the change. **A cut and an addition have
   opposite success conditions.** For a cut, success is the absence of
   replicated degradation: the sign count must not favor the pre-cut version.
   Demanding that a cut clear the noise floor is incoherent, because a good cut
   leaves the delta near zero. For an addition or a keep decision, success is
   replicated improvement whose magnitude clears the floor.
4. If the rule is fenced, update the fence in the same commit. The
   `software-engineering-library` skill currently fences the three book rules.

## Step 5. Adversarial review

Run a review with the model that did not produce the change. Sol reviewing
Claude's work and the reverse both surface things a single model misses.

Give the reviewer the claim, the evidence, and explicit permission to reject
it. A prompt that asks "review this" gets agreement. The working shape:

- State what the branch claims, including the reasoning, not just the diff.
- Name the specific arguments to attack, one per section.
- Include the numbers and ask whether they support the conclusion.
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

- **Judge failures used to score as zero.** One unparseable sample out of three
  zeroed a whole cell, and zeroed cells were averaged into the mechanism mean.
  Because failures are not evenly distributed across mechanisms, this could
  invert the ranking. Fixed on 2026-07-29. Any result file older than that with
  a non-zero `total_judge_failures` has a biased table.
- **A four-backtick fence was miscounted and refused.** The fence matcher took
  runs of exactly three backticks, so a payload fenced with four (legal
  Markdown, and what a judge emits when its own reasoning quotes a
  three-backtick block) closed at the inner three and yielded a truncated body
  that would not parse. The sample was dropped. Found by adversarial review
  round 11, and first recorded here rather than fixed on the reasoning that
  widening the matcher would re-introduce the candidate-selection choice the
  exactly-one-fence rule exists to remove. **That reasoning was wrong**, and
  round 12 showed why: pairing the close to the width of the run that opened
  it collects every block exactly as before and still refuses anything other
  than one, so no selection returns. Fixed on 2026-07-30. The archive is
  unaffected either way, since no stored payload contains a four-backtick run
  (measured: 0 of 24 prefixes).
- **A lone fence outranked an unfenced verdict beside it.** Requiring exactly
  one fenced block removed the choice among fences and left the choice between
  the fence and the prose around it. A judge that wrote its verdict as
  unfenced text and fenced a rubric exemplar it had labelled "do not use" was
  answered with the exemplar, which then parsed cleanly and was published as a
  recovered sample. Unwrapping now also requires that nothing but whitespace
  sit outside the fence: that is the only condition under which unwrapping is
  a rewrite of the payload rather than a choice within it. Found by
  adversarial review round 13, fixed on 2026-07-30. The archive is unaffected,
  since none of the stored payloads contains a fence at all (measured: 0 of 24
  prefixes), and all 24 recover to byte-identical triples afterwards.
- **A clean parse was treated as proof of a single answer.** Eleven rounds
  attacked recovery and left the strict parse alone, on the reasoning that a
  payload which parses whole cannot be ambiguous. JSON nests, so it can: a
  second verdict sits inside the first as a member, a list element, or a
  quoted string, and the grammar is satisfied. Duplicate-key rejection does
  not see these, because a nested key is not a repeated one. The guard that
  refuses exactly this already existed and was wired into all three recovery
  paths and none of the strict one, so the miss was a path that did not know
  it needed a check rather than a missing check. It now runs once before any
  parse. Found by adversarial review round 14, fixed on 2026-07-30. **Unlike
  the sixteen before it, the cost against the published table is unknown**:
  the archive stores raw payloads only for failed samples, so the 264
  successful ones cannot be replayed (issue #3998). Refusing on any `\u` in
  the payload carries a second unmeasured cost in the same direction, since a
  healthy verdict whose reasoning contains an escape now refuses too.
- **Agentic CLI output is not clean JSON.** The provider reads
  `~/.copilot/session-state/<uuid>/events.jsonl` and correlates by the sandbox
  working directory, which is race-free. Falling back to stdout parsing mixes
  tool traces into the answer. That fallback also fires on a filesystem error,
  silently skipping the only check that confirms which model actually served
  the request, so a run can be attributed to the wrong model with no warning
  (issue #3959).
- **The Copilot CLI stdout token counter is non-monotonic.** Unusable as a
  measurement. Use the event log instead: in
  `~/.copilot/session-state/<uuid>/events.jsonl`, read `data.totalNanoAiu` on
  events whose `type` is `session.usage_checkpoint`. Verified against 3253
  local sessions, which carry 2729 such events. `session.usage_checkpoint` is
  the value of `type`, not a nested key, so a walker looking for a literal
  `session` key at the root finds nothing.
- **The CLI loads `AGENTS.md` from its working directory.** Eval calls must run
  in an empty temp directory or the repo's own instructions contaminate the
  baseline mechanism. User-level instructions in `~/.copilot/` ignore the
  working directory entirely and need `--no-custom-instructions`. Runs archived
  before 2026-07-29 predate that flag; see Step 1 for what that means for them.
- **Most eval entry points still demand `ANTHROPIC_API_KEY`** even when
  `EVAL_PROVIDER` selects a keyless provider. Tracked in issue #3924.
  `eval-rule-activation.py` is fixed and shows the pattern.

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

<!-- vendor-portability: declared. The provenance table cites .agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the archive holding the eight runs behind the published numbers, so a reader can re-derive every cell instead of taking them on faith. It is a citation in a narrative, not a path the skill reads or writes. A vendored install loses the ability to check the raw artifacts locally; the procedure still runs, it just produces new data rather than reproducing ours. Issue #2050. -->
