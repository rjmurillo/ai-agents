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

| Mechanism | System prompt | Answers |
|---|---|---|
| `baseline` | empty | What does the model do unprompted? |
| `description` | frontmatter only | Does the routing line alone suffice? |
| `full` | whole rule body | Does the body add anything? |

**The comparison that decides the question is `description` against `full`.**
If they tie, the body is dead weight and belongs in progressive disclosure.
`baseline` tells you whether the rule was ever needed at all.

## Step 2. Read the table honestly

```
| Mechanism    | Pos avg | Neg avg | Δ vs baseline | Graded |
|--------------|---------|---------|---------------|--------|
| baseline     |    3.83 |     5.0 |               |    3/3 |
| description  |    3.67 |     5.0 |         -0.16 |    3/3 |
| full         |    4.11 |     5.0 |         +0.28 |    3/3 |
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

Measured 2026-07-29 on `unified-software-engineering.json`, two identical
Opus 5 runs:

| Run | baseline | description | full |
|---|---|---|---|
| A | 3.78 | 3.89 (+0.11) | 3.89 (+0.11) |
| B | 3.83 | 3.67 (-0.16) | 4.11 (+0.28) |

The `description` delta **flipped sign between identical runs**. Run-to-run
swing was about 0.27, which is larger than most effects worth arguing about.

**Practical rule: at 3 positive scenarios, treat any delta under roughly 0.3
as noise.** Do not cut or keep content on a smaller signal. To resolve
something smaller, add scenarios or repeat runs and report the spread.

Other limits, all real:

- **n is 3 or 4 positive scenarios per rule.** One cell moves the average a
  lot.
- **The judge is the same model family being evaluated.** Treat it as a known
  validity weakness, not a settled one.
- **Per-cell scores are a median of 3 judge samples.** That smooths judge
  noise, not model noise. Model noise needs repeat runs.
- **A single run reports no variance.** The script gives you a point estimate
  with no error bar. Run it at least twice before believing a delta.

## Step 3. Decide

| Evidence | Action |
|---|---|
| `description` ties or beats `full`, replicated across runs | Move the body to progressive disclosure |
| `full` beats `description` by more than the noise floor, replicated | Keep the body, record the number |
| Delta under the noise floor | **Not resolved.** Do not cut. Say so plainly |
| No scenario file exists | **Cannot be gated.** Write scenarios first |

The last row is the common case and the easy one to skip. As of 2026-07-29,
`code-quality.md` (14,152 bytes) and `pragmatic-programmer.md` (12,219 bytes)
have no scenario file at all. They are the two largest always-on rules. They
cannot be audited until someone writes scenarios for them.

Applying the doctrine to **authoring guidance** is a separate decision from
**cutting existing content**. The first is an argument about where new content
should go and does not need an eval. The second changes measured behavior and
does.

## Step 4. Prove the delta

After any change to always-on content:

1. `uv run python build/scripts/generate_rules.py` to refresh the mirrors.
2. Re-run Step 0 and record the byte delta.
3. Re-run Step 1 on both models and confirm the change cleared the noise floor.
4. If the rule is fenced, update the fence in the same commit.
   `.claude/skills/software-engineering-library/SKILL.md` currently fences the
   three book rules.

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

These each cost real time. They are fixed, but the shapes recur.

- **Judge failures used to score as zero.** One unparseable sample out of three
  zeroed a whole cell, and zeroed cells were averaged into the mechanism mean.
  Because failures are not evenly distributed across mechanisms, this could
  invert the ranking. Fixed on 2026-07-29. Any result file older than that with
  a non-zero `total_judge_failures` has a biased table.
- **Agentic CLI output is not clean JSON.** The provider reads
  `~/.copilot/session-state/<uuid>/events.jsonl` and correlates by the sandbox
  working directory, which is race-free. Falling back to stdout parsing mixes
  tool traces into the answer.
- **The Copilot CLI stdout token counter is non-monotonic.** Unusable as a
  measurement. Use `session.usage_checkpoint.data.totalNanoAiu` from the event
  log instead.
- **The CLI loads `AGENTS.md` from its working directory.** Eval calls must run
  in an empty temp directory or the repo's own instructions contaminate the
  baseline mechanism.
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
