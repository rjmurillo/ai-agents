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

```text
| Mechanism    | Pos avg | Neg avg | Δ vs baseline | Pos graded | Neg graded |
|--------------|---------|---------|---------------|------------|------------|
| baseline     |    3.89 |     5.0 |               |        3/3 |        1/1 |
| description  |    3.67 |     5.0 |         -0.22 |        3/3 |        1/1 |
| full         |    4.11 |     5.0 |         +0.22 |        3/3 |        1/1 |
```

Check in this order:

1. **`gating_judge_failures` must be 0.** A non-zero gating count means a cell
   the verdict rests on went ungraded, and the verdict says
   `FAIL_JUDGE_ERRORS`. `total_judge_failures` may exceed it, counting `full`
   on a routed target and `baseline` on the negative pool, neither of which
   gates anything. The table names the excluded cells when the counts differ.
2. **The negative average must clear the floor on every reachable mechanism.**
   Checked before coverage: observed harm outranks an unproven benefit. The
   gate is a mean over the whole negative pool against `MIN_RESTRAINT_SCORE`,
   so one low scenario among high ones need not fail it. For a skill reference
   the gate reads `description` only: `full` force-injects what routing omits.
3. **The graded columns must read `n/n`.** An off-rubric cell is unmeasured, so
   it leaves the average without raising `judge_failed`, and a mean over one
   scenario looks identical to a mean over three. Each pool is gated on the
   mechanisms its verdict names: the negative pool on what the target can
   reach, the positive pool on `baseline` and `description` only, never `full`.
4. **Only then read the deltas**, against the noise floor below.

## What the instrument can and cannot resolve

Moved to `rule-audit-instrument.md`. **Read it before believing any number the
eval prints.** It covers the noise floor, the single-shot judge, which
comparisons the harness can and cannot settle, and how each gate is scoped to
the population its verdict names.

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

Moved to `rule-audit-instrument.md`. Each one cost real time; the ones carrying
an open issue number are still open, and the shapes recur either way.

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

<!-- vendor-portability: declared, and this one is an executable dependency, not a citation. Four commands in this file invoke upstream-only scripts: scripts/validation/instruction_budget.py (twice), scripts/eval/eval-rule-activation.py, and build/scripts/generate_rules.py. None of the three trees ships in any plugin root, so a vendored install cannot run this procedure at all. That is intended. The procedure audits the rjmurillo/ai-agents rules corpus against this repo's own generated mirrors and scenario fixtures, so its audience is repo contributors working in a full checkout. SKILL.md labels the routing trigger contributor-only for the same reason. Do not resolve this by moving the eval harness under the skill: scripts/eval is 23k lines across 80 files, three workflows and check_rule_activation_coverage.py depend on it, and the parity requirement would ship a second byte-identical copy to every consumer. Issue #2050. -->
