---
name: ai-agents-research-methodology
version: 1.0.0
license: MIT
description: How a hunch becomes an accepted result in this repo. Covers the
  evidence bar, hypothesis-predicts-numbers discipline, and the idea lifecycle
  from contradiction log through probe, eval baseline, ADR debate, calibrated
  gate, and post-ship monitoring. Use when you say `how do I prove this
  idea`, `run the idea lifecycle`, `what is the evidence bar`. Do NOT use for
  the open research programs (use ai-agents-research-frontier) or probe recipe
  depth (use ai-agents-empirical-probe-toolkit).
---

# AI Agents Research Methodology

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This repo runs on verification-based governance: labels like "MANDATORY" or
"NON-NEGOTIABLE" are insufficient, every requirement needs a verification
mechanism. The same standard applies to ideas. An idea is not accepted because it sounds
right, because a model agreed with it, or because a retro asserted it. It is
accepted when it survives the lifecycle below and leaves an inspectable
artifact at every stage.

This skill is the discipline. For the specific probe recipes, use
`ai-agents-empirical-probe-toolkit`. For the three open research programs, use
`ai-agents-research-frontier`. For the archive of past settled results, use
`ai-agents-failure-archaeology`.

## Triggers

- `how do I prove this idea`
- `run the idea lifecycle`
- `what is the evidence bar`
- `turn this hunch into a result`

## The Evidence Bar

A result is accepted here when ONE mechanism explains ALL observations,
including the negative ones, and the explanation survives adversarial
refutation. Partial explanations that cover only the confirming observations
are hypotheses, not results.

The cautionary tale is PR #1989. Mitigation M1 was built on a root-cause claim
inherited from a retro RCA that nobody re-verified: the RCA said pagination was
missing, but `get_unresolved_review_threads.py` already paginated correctly
(.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:20). Five
commits were spent building on the false premise. The mechanism-check that
would have caught it costs one file read.

Map each claim type to the adversarial machinery that already exists. Do not
invent a new review ritual; route into these:

| Claim type | Adversarial mechanism | How to invoke |
|---|---|---|
| Architectural decision (ADR) | `adr-review` 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) until consensus, 10 rounds max | Auto-fires on any `ADR-*.md` create/edit (AGENTS.md "ADR Review"); or `/adr-review path` |
| A single decision's reasoning | `decision-critic` skill | Say `Poke holes in this decision` or `Validate my thinking on ...` |
| Contrarian read of a plan | `independent-thinker` or `critic` agent (`.claude/agents/`) | Task tool with that subagent_type |
| Strategic build/buy/defer | `buy-vs-build-framework` (Quick tier: 1-2 hours) | Required gate for new capabilities, see Phase 3 |
| "Why does this constraint exist" | `chestertons-fence` | Before proposing removal of anything settled |
| Behavioral claim about a prompt or rule | Eval harness (ADR-057) | See Predict Numbers Before Running |
| Prose claims in the write-up | `prose-self-check`, `doc-accuracy` | Before emitting the artifact |

## Predict Numbers Before Running

Write the predicted outcome down BEFORE running the measurement. A prediction
made after seeing the data is a description, not a test. Concretely:

1. State the hypothesis and the number it predicts (pass-rate delta,
   activation score, firing rate) in the session log or spike note.
2. Validate the setup with zero spend first:

   ```bash
   uv run python scripts/eval/eval-prompt-change.py \
     --prompt templates/agents/analyst.shared.md \
     --scenarios tests/evals/analyst-scenarios.json \
     --base-ref main --dry-run
   ```

   (Both paths exist in-tree; there is no per-skill scenario fixture for every
   prompt. Substitute your own prompt path and a real `tests/evals/*.json`
   fixture; `ls tests/evals/` lists what is available.)

   `--dry-run` validates inputs and makes no API calls
   (scripts/eval/eval-prompt-change.py:567). It is the only no-spend path;
   there is no `--mock`.
3. Run the real eval, compare against the written prediction, and record both
   in the write-up. A miss is a finding, not an embarrassment.

Available instruments (all under `scripts/eval/`, verified 2026-07-03):
`eval-prompt-change.py` (before/after scenario judgment per ADR-057),
`eval-agent-vs-baseline.py` (agent prompt vs fixed baseline),
`eval-rule-activation.py` (does a `.claude/rules/*.md` file actually change
behavior: baseline vs description-only vs full-body, judged on activation,
citation, behavior). Interpretation guidance lives in
`ai-agents-diagnostics-toolkit`.

## Process

The lifecycle. Every stage produces an artifact; every transition has a gate.
Skipping a stage is how #1989 happened.

### Phase 1: Hunch, Then Search, Then Contradiction Log

Before building anything, search: this codebase, Serena memories
(`memory-search`), ADRs, then external docs
(.claude/rules/search-before-building.md). Most hunches die here because the
answer already exists; that is a cheap success.

If your first-principles position contradicts the conventional answer (an ADR,
a memory, a canonical pattern), log it before proceeding: Serena memory named
`decision-<short-slug>` with five fields: question, conventional answer with
citation, first-principles position, evidence, decision. The log is what stops
the next agent from silently reverting your result.

### Phase 2: Spike With an Empirical Probe

Turn the hunch into a falsifiable claim and probe it. Rules of the probe
(recipes and worked examples in `ai-agents-empirical-probe-toolkit`):

- Run against the real tool at a pinned version, under foreign cwd/env, not in
  the comfortable default environment.
- Include a negative control: a case that proves the probe CAN fail.
- Never trust vendor docs alone; this repo was burned twice by
  wrong-by-omission docs (#2205, #2290 retros in `.agents/retrospective/`).
- Record the probe result in a decision memory with version and date.

### Phase 3: Capability Gate and Eval Baseline

If the idea adds a new capability (Context, module, scanner, validator,
pipeline component), it must pass the buy-vs-build gate BEFORE any spec work.
AGENTS.md (line 40): "buy-vs-build Quick tier BEFORE spec-generator + baseline;
greater than 13wk no baseline = prune. Skip: bug, doc, refactor, approved
extension." Run `buy-vs-build-framework` at Quick tier (1-2 hours: Core vs
Context, simple TCO, go/no-go).

Then establish the eval baseline using the Predict Numbers discipline above.
An idea that has carried no measurable baseline for 13 weeks gets pruned; that
is the documented cost of skipping this phase.

### Phase 4: ADR and Debate

If the result changes architecture, policy, or a public contract, write the
ADR with `adr-generator`. Saving the file fires `adr-review` automatically:
six agents debate in structured rounds until consensus or 10 rounds. Do not
route around the debate by encoding the decision in a rule file or skill
instead; governance changes need human approval, an ADR, consensus, and a
cited failure mode. Route the change itself through
`ai-agents-change-control`.

Beware historical trap: ADR numbers have collided. Verify content, not number,
when citing.

### Phase 5: Ship as a Gate or Skill, With Calibration

A result becomes enforcement (a hook, a validator, a CI gate) or capability (a
skill via `SkillForge`). Any threshold-based detector must ship with a
calibration table. The rule, from the #1989 retro (Process Change 3,
.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:149-157): show
the threshold, a sample of real PRs measured against it, and the expected
firing rate. "A detector that cannot fire on the last 5 PRs in the repo is not
calibrated." The origin: M4 shipped with threshold 6 in a repo whose busiest
PR had 4 file edits; it could never fire (retro lines 72-73).

Also run the new guard on its own branch before merging. #1989 M5 was a
pre-push guard that was never executed on the branch that shipped it.

### Phase 6: Monitor

Enforcement decays. The push guards used to emit `EVENT=` telemetry lines
(stderr, via `push_guard_base.py`) that a maturity-tier skill aggregated into
tiers (Budding, Growing, Mature, Proficient, Inert, Harmful) to tell you
whether a gate earned its keep. That emitter, every guard built on it, and the
classifier skill itself were deleted under ADR-084 (issue #5154): there is no
producer and no consumer today. The underlying principle still applies to
whatever gate you add next: an Inert gate is a candidate for the same prune
rule as an unbaselined idea. If you build a new detector, ship its own
telemetry and monitoring alongside it; measurement tooling for the surviving
instruments lives in `ai-agents-diagnostics-toolkit`.

### Phase 7: Adopt, or Retire With a Record

Both outcomes are results. Adoption means the artifact set is complete: probe
memory, eval numbers, ADR (if governance), calibrated gate, monitoring hook.

Retirement gets recorded, never silenced. The exemplar is issue #2230: a
launcher-level fail-open wrapper was proposed, evaluated, and REJECTED as a
silent-failure anti-pattern; the rejection is recorded with rationale in the #2205 retro decision table
(.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:411) and
the binding principle lives in `.claude/rules/generated-artifacts.md`. Because
the rejection was written down, nobody re-proposes it. An unrecorded rejection
is a future duplicate proposal.

## Lifecycle at a Glance

| Stage | Artifact | Gate to next stage | Who/what approves |
|---|---|---|---|
| 1. Hunch | `decision-<slug>` Serena memory (contradiction log) | Search done; contradiction logged if any | Self-serve |
| 2. Spike | Probe script + decision memory with version/date | Negative control passed; claim falsifiable | Self-serve, peers via memory |
| 3. Baseline | Buy-vs-build Quick verdict + written prediction + eval numbers | Go verdict; baseline exists (13wk prune clock starts) | `buy-vs-build-framework` output; user for spend |
| 4. ADR | `ADR-*.md` + debate log | `adr-review` consensus (max 10 rounds) + human approval | 6-agent debate + user |
| 5. Ship | Gate/skill + calibration table + tests | `ai-agents-change-control` ladder (pre_pr.py, CI, plugin version-field gate if plugin tree) | CI gates + review |
| 6. Monitor | Detector-specific telemetry and tier report | Tier not Inert/Harmful | Periodic report from whatever the detector ships |
| 7. Adopt/retire | Retro or rejection record | n/a (terminal) | Documented either way |

## Where Good Ideas Historically Came From

- **Retro mining.** `.agents/retrospective/` is the
  richest vein; `ai-agents-failure-archaeology` indexes the major ones.
  Retro-cited short SHAs do not resolve locally even with full history present
  (~1471 commits as of 2026-07-03), so retros and memories, not `git log`,
  are the archaeology surface.
- **User corrections.** Every "no" or "wrong" is a candidate pattern; the
  `reflect` skill captures them with confidence levels.
- **Incident postmortems.** The `retrospective` skill turns an incident into
  Five-Whys evidence; the guard framework, `pre_pr.py`, and the anchoring
  contract all trace to specific incidents.
- **Cross-model disagreement.** When Claude and another model disagree, or
  agree against the user's direction, that is signal, not a mandate. Per
  `.claude/rules/builder-ethos.md` (User Sovereignty): present the
  recommendation, state what context you may be missing, and ask. Never act on
  model consensus alone.

## Writing Up Results

Route write-ups through the documents of record (`ai-agents-docs-of-record`
for templates and house style). Non-negotiables for research prose:

- No oversell. Proposed things stay labeled: ADR-069 carries
  `status: proposed` (as of 2026-07-03); citing it as settled is a defect.
- Date-stamp volatile facts inline: "(as of 2026-07-03)".
- Quote canonical sources verbatim when claiming a mirror "matches" (FM-9,
  `.agents/governance/FAILURE-MODES.md`; PR #1887 paid 7 fix commits for
  paraphrases).
- Include the prediction AND the measured number, even when they disagree.
- Run `prose-self-check` before emitting.

## Anti-Patterns

| Anti-pattern | Real instance | Correct move |
|---|---|---|
| Building on an unverified RCA | #1989 M1: "missing pagination" premise was false; the script already paginated | Re-verify the mechanism against source before building on it |
| Shipping an uncalibrated threshold | #1989 M4: threshold 6, repo max 4, could never fire | Calibration table against last 5 merged PRs, in the PR description |
| Guard never run on its own branch | #1989 M5 pre-push guard | Execute the guard on the shipping branch before merge |
| Prediction written after the run | Any post-hoc "as expected" | Prediction in session log BEFORE the eval command |
| Adopting on model consensus | Rejected repeatedly per builder-ethos | Present, state missing context, ask the user |
| Silent retirement | The failure #2230's explicit rejection record prevents | Record rejections with rationale where the next proposer will search |
| Routing around the debate | Encoding policy in a rule to dodge `adr-review` | ADR + debate + human approval for governance changes |
| Trusting vendor docs over probes | #2205 first fix assumed an env var by analogy; shipped 3 new defects | Empirical probe with negative control (`ai-agents-empirical-probe-toolkit`) |

## Verification

Before calling an idea "an accepted result," confirm:

- [ ] A written prediction predates the measurement, and both numbers appear in the write-up.
- [ ] One mechanism explains all observations, including negatives, and survived at least one adversarial pass (`adr-review`, `decision-critic`, or `independent-thinker`).
- [ ] New capability passed the buy-vs-build Quick tier gate and has an eval baseline (or the 13-week prune clock is acknowledged).
- [ ] Any threshold detector ships with a calibration table against the last 5 merged PRs and was run on its own branch.
- [ ] The outcome (adoption or rejection) is recorded in a document of record with date-stamped, non-oversold claims.

## Provenance and Maintenance

Verified 2026-07-03 against the working tree. Re-verify before relying on
volatile facts:

| Fact | Source | Re-verify |
|---|---|---|
| #1989 false premise, calibration rule, M4 numbers | `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:20,72-73,149-157` | `grep -n "calibrat" .agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` |
| #2230 rejection record | `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:411` | `grep -n 2230 .agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` |
| adr-review auto-fire + 6-agent debate | AGENTS.md "ADR Review"; `.claude/skills/adr-review/SKILL.md` | `grep -n "debate" .claude/skills/adr-review/SKILL.md` |
| buy-vs-build Quick tier gate + 13wk prune | `AGENTS.md:40`; `.claude/skills/buy-vs-build-framework/SKILL.md:66` | `grep -n "13" AGENTS.md` |
| eval scripts and `--dry-run` | `scripts/eval/eval-prompt-change.py:567`; `scripts/eval/` listing | `ls scripts/eval/ && grep -n "dry-run" scripts/eval/eval-prompt-change.py` |
| Contradiction log format | `.claude/rules/search-before-building.md` | `grep -n "decision-" .claude/rules/search-before-building.md` |
| ADR-069 still proposed | `.agents/architecture/ADR-069-context-corpus-is-the-product.md:2` | `head -5 .agents/architecture/ADR-069-context-corpus-is-the-product.md` |
| Retro corpus size | `.agents/retrospective/` | `python3 -c "import pathlib;print(sum(1 for p in pathlib.Path('.agents/retrospective').glob('*.md') if p.name != 'INDEX.md'))"` |

Uncertainty flag: the `EVENT=` telemetry consumer pipeline was never fully
mapped before it was retired (noted in `ai-agents-research-frontier`). The
emitter, `push_guard_base.py`, was verified present 2026-07-03 (mirrored under
`src/copilot-cli/hooks/PreToolUse/`) and was deleted from both trees under
ADR-084 (issue #5154), along with the tier-classifier skill that consumed its
output; nothing in this repo produces or reads that telemetry today.
