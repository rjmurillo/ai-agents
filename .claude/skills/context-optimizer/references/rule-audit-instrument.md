# Rule Audit Instrument

What the eval harness can measure, what it cannot, and the traps that have
cost real time. Companion to `rule-audit-procedure.md`, which is the procedure
you follow; this document is the instrument you follow it with. Read the first
section before believing any number the eval prints.

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

**So run the eval four times per model and count signs.** A
consistent direction across runs is evidence. A large delta in one run is not.
This is the reading that survived the noise in the one audit run so far, and it
was chosen after seeing those runs, so those runs generated the rule and cannot
also test it.

#### Registered decision rule, 2026-08-03

Fixed here before the next audit runs, which makes that audit this rule's first
confirmatory test (issue #3957). Editing any line below after seeing a run
makes that run exploratory too, so change it before, or not at all.

- **Run count.** Exactly four runs per model across two model families, eight
  signs in total. Runs are not added because the count came out close, and a
  run is discarded only for a recorded provider error, never for its result.
- **The unit.** One run contributes one sign: the direction of that run's delta
  between the two arms being compared. Magnitudes are recorded and do not vote.
- **Ties.** An exact tie contributes no sign and lowers n. That is the sign
  test's own convention, and it is why the `description` row above reads as one
  win against four losses rather than one against seven.
- **Tails.** Two-tailed, always. A direction is declared before the run and is
  not rescored one-tailed afterwards. The 2026-07-29 result ran against the
  predicted direction, which is the case a one-tailed reading mishandles.
- **Threshold for an addition or a keep.** The deciding outcomes are exactly 8
  of 8, 7 of 8, 7 of 7, 6 of 6, and 5 of 5 non-tied signs in one direction,
  whose two-tailed p values under a fair-coin null are 0.008, 0.070, 0.016,
  0.031, and 0.063. Every other outcome does not decide. With four or fewer
  non-tied signs even unanimity reaches only 0.125, so an audit that ties its
  way down to an n of 4 is repeated rather than read.
- **Threshold for a cut.** A cut fails when the pre-cut version wins the sign
  count at that same threshold, and passes otherwise. This accepts a null and
  cannot separate "no degradation" from "too few runs to see one". The fixed
  run count is what keeps that blind spot the same size in every audit.

Scored against this rule, the 2026-07-29 result is 7 of 8 for `full` over
`description` at an n of 8, p 0.070, which is a deciding outcome. It is still
recorded as the hypothesis rather than as a pass, because the rule was written
after the runs.

### The eight runs, for comparison

Recorded so a later re-run has something to compare against. Scenario is
`unified-software-engineering`, three positive cells plus one negative,
one generation per cell, judge samples medianed. Scores are 0 to 5.

The numbers below are the positive-scenario average. **They came from a
reduction the instrument no longer uses**, and reproduce only in that order:

1. The judge returns three fields per sample: `activation_score`,
   `citation_score`, `behavior_score`.
2. Per cell (one scenario x one mechanism), take the **median** across judge
   samples of each field separately. Three medians.
3. The cell score is the **mean of those three medians**.
4. The published figure is the **mean of the three positive-scenario cells**
   for that mechanism. The negative scenario was scored but did not gate.

Nine medians per run is why a run lands on a 1/9 grid: 3.89 is 35/9.

**Step 2 was a defect, not a choice, and the numbers below carry it.** A
coordinate-wise median need not be any sample the judge gave: three samples of
5/5/1, 5/1/5, and 1/5/5 reduce to 5/5/5, a cell of 5.0, when every judge rated
the triple at 3.67. Reducing each sample to its own mean first and medianing
those scalars gives 3.67. Across all 96 archived cells **3 diverge**, worst by
0.333 on a cell and 0.111 on a run average (`t-sol56` S2 description and S3
baseline, `var-sol-2` S3 full). Recomputed end to end the sign count holds at
seven positive against one negative, p = 0.0703; two rows shift.

**Both defects are now fixed (issues #3989 and #3933).** Post-fix runs carry a
`cell_score` reduced in that second order; with an even sample count that median
is a midpoint, so it need not be a score any judge returned. Negative scenarios
now gate. Archived runs carry no `cell_score`, so the reader falls back to the
mean of three medians and reports the substitution; those runs are a closed
record and restating one under a rule it was not computed with would be a
fabrication. A `cell_score` present but null or off the rubric never came from
the writer, so it is damage, and the cell reads as unmeasured. **Distrust the
archived cells at the 0.1 level and do not edit them.**

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

The full accounting and the confounds it creates for the table above are in
`rule-audit-evidence.md`. Read it before citing a cell from this table. The
defects found in the verdict-parsing code, across more than twenty review
rounds,
are in `rule-audit-parser-forensics.md`. Each one's cost against this table was
measurable, because this run's archive stores the raw judge payload for all 288
samples, successes included, so a defect on the success path can be replayed
rather than argued about. Issue #3998 was filed on the belief that the archive
kept raw only for failures; that belief was wrong for this run, and the general
concern it raises applies only to a future instrument that discards
success-path evidence.

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
  above is exploratory. The rule is now registered above and dated 2026-08-03,
  which makes the first audit run after that date its first confirmatory test
  (issue #3957). These eight runs stay exploratory whatever that audit returns.
- **The judge is the same model family being evaluated.** A known validity
  weakness, not a settled one.
- **Per-cell scores are a median of 3 judge samples.** That smooths judge
  noise, not model noise. Model noise needs repeat runs.
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
  was not fully graded. Only a mechanism covering the whole negative pool sets
  the floor, so measured harm outranks coverage while a partly graded pool
  reads as incompleteness. An unproven harm outranks an unproven benefit.
  **Vacuous here**: the lone negative scenario scored 5.0. Unit tests cover it.

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
  that would not parse. The sample was dropped. Recorded rather than fixed at
  first, on the reasoning that widening the matcher would re-introduce the
  candidate selection the exactly-one-fence rule exists to remove. **That
  reasoning was wrong**: pairing the close to the width of the run that opened
  it collects every block exactly as before and still refuses anything other
  than one, so no selection returns. Fixed on 2026-07-30, archive unaffected
  (measured: 0 of 24 prefixes carry a four-backtick run).
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
  parse. Found by adversarial review round 14, fixed on 2026-07-30. **Its cost
  against the published table is zero, and unlike the sixteen before it that
  is measured rather than argued**: `recovered-judge-payloads.json` holds the
  full original for all 288 samples, not only the failures, so the 264
  successes replay directly. None of the 264 trips either duplicate-name guard,
  none is refused by the current parser, and none contains a literal `\u`, so
  the escape-refusal carries no cost either. Issue #3998 was filed when the
  archive was believed to keep raw only for failures; it does not apply to this
  run.
- **Agentic CLI output is not clean JSON.** The provider reads
  `~/.copilot/session-state/<uuid>/events.jsonl` and correlates by the sandbox
  working directory, which is race-free. The stdout fallback used to mix tool
  traces into the answer, and it skipped the check that confirms which model
  served the request, so a run could be attributed to the wrong model with no
  warning (issue #3959, closed). Both are refused now rather than graded. A
  stdout reply whose line opens with a CLI trace marker is refused, and so is a
  reply whose model the run cannot confirm, unless an operator sets
  `EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL` and takes that loss knowingly. The
  archived runs predate both gates, which is why their attribution still rests
  on the filename.
- **One session log can hold more than one model.** Sub-agents run their own
  models and write into the parent's log, and interactive logs here carry up to
  eleven distinct models in a single file. They are marked: the event carries a
  top-level `agentId` and the message carries `data.parentToolCallId`. In a
  sampled session both marked exactly the same 671 events, while the 4465
  messages carrying neither were all the primary model. The provider skips
  them, because their text is internal working output and never the answer.
  Read a log the same way, or you will count a sub-agent's model as the one
  that replied.
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
- **The archive nests dicts where a walker expects lists.** `rules` is a dict
  keyed by rule name, and each scenario's `mechanisms` is a dict keyed by
  `baseline`/`description`/`full`. Only `scenarios` is a list. A walker that
  assumes lists finds zero samples and prints a clean result from no data,
  which is the same failure class as the parser defects in the evidence
  document: a confident answer derived from nothing. Reading
  `rules[<name>].scenarios[].mechanisms[<mech>].score_samples[]` and
  re-medianing each cell reproduces the published table exactly.
- **Recovering discarded samples.** Failed samples store the truncated raw
  payload in `reasoning` behind a `judge parse error:` prefix that ends with a
  single space; strip the whole prefix and feed the remainder to
  `_salvage_scores`. Successful samples store no payload
  in the artifact at all. Both are recovered in full in
  `recovered-judge-payloads.json` beside it, keyed by the same coordinates and
  attributed by the input-based oracle rather than by the score.

<!-- vendor-portability: declared. Three citations in narrative, none of them a path the skill reads or writes. .agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ is the archive holding the eight runs behind the published numbers, so a reader can re-derive every cell instead of taking them on faith. scripts/eval/README.md is the record of the same-text variance measurement that sets the noise floor. scripts/eval/_copilot_cli.py is the transport that produced every archived run, named so a reader can see which knobs it drops. A vendored install loses the ability to check any of the three locally; the procedure still runs, it just produces new data rather than reproducing ours. Issue #2050. -->
