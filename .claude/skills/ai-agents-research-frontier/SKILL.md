---
name: ai-agents-research-frontier
description: "Three ranked open research programs for this repo, each with honest current-state evidence, first concrete steps, and a falsifiable milestone. Verified governance (ADR-069, proposed), cross-harness abstraction (ADR-072 and ADR-068, accepted), and the self-improving loop. Use when you say `research frontier`, `open problems`, `what should we research next`. Do NOT use for how to run an experiment here (use `ai-agents-research-methodology`)."
version: 1.0.0
license: MIT
metadata:
  distribution: repo-local
  routing:
    role: conditional-adjunct
    invoker: ai-agents-research-methodology
    trigger: ai-agents-research-methodology points here for the open research programs
    user-facing: false
---

# AI Agents Research Frontier

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers -->
Open problems where this repository can advance the state of the art, ranked in
owner-confirmed priority order. This skill tells you WHAT is worth working on and
what "done" would look like. It does not teach experiment discipline (that is
`ai-agents-research-methodology`) and it is not the portability battle plan
(that is `ai-agents-portability-campaign`).

Honesty contract for this document: every asset claim below was re-verified
against the working tree at 42e409325 on 2026-10-31. Anything labeled PROPOSED is not policy.
Anything labeled UNVERIFIED could not be confirmed and must be checked before you
build on it.

## Triggers

- `research frontier`
- `open problems`
- `what should we research next`
- `frontier programs`

## The Three Programs at a Glance

| Rank | Program | Anchor artifacts | Status (HEAD 42e409325, 2026-10-31) | Falsifiable milestone (short form) |
|------|---------|------------------|---------------------------|-------------------------------------|
| 1 | Verified governance | ADR-069, `scripts/eval/eval-rule-activation.py` | ADR-069 is PROPOSED; eval tool and rule scenario fixtures exist (count: `corpus-counts`) | Controlled eval shows gated-corpus sessions beat ungated on N scenarios with defensible stats |
| 2 | Cross-harness abstraction | ADR-072, ADR-068, `build/generate_agents.py`, `tests/build_scripts/test_generate_hooks_runtime_contract.py` | ADR-072 and ADR-068 ACCEPTED; generators and contract tests exist and run | New harness target added with zero hand-edits to generated trees, contract suite green |
| 3 | Self-improving loop | `reflect`, `memory-search`; hooks and `EVENT=` telemetry retired (ADR-097, ADR-084) | Tool-call hooks retired; no producer or consumer pipeline | A correction observed once auto-proposes a guard that survives calibration |

## Process

### Phase 1: Verify current state before claiming anything

The evidence below decays. Re-run these before quoting any of it in an ADR,
issue, or write-up. All commands run from the repo root.

| Claim | Re-verify command |
|-------|-------------------|
| ADR-069 status is proposed | `head -5 .project-toolkit/architecture/ADR-069-context-corpus-is-the-product.md` |
| ADR-072 status is accepted | `sed -n '1,15p' .project-toolkit/architecture/ADR-072-jtbd-plugin-architecture.md` |
| ADR-068 status is accepted | `sed -n '1,10p' .project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md` |
| Rule-activation eval exists with a no-spend path | `python3 scripts/eval/eval-rule-activation.py --help` |
| Runtime contract tests pass | `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q` |
| Tool-call hooks retired (ADR-097) | `ls .claude/hooks/PreToolUse/` expects no `invoke_*_guard.py` |

Counts come from the dispatcher; see Scripts below.

### Phase 2: Pick a program

Take the highest-ranked program whose first unclaimed step you can finish. Rank
order is owner-confirmed; do not reorder it without the owner. If your idea does
not fit any program, it is a new capability: route through the
`buy-vs-build-framework` Quick tier gate first (AGENTS.md Skill-First section),
then `ai-agents-research-methodology` for the idea lifecycle.

### Phase 3: Execute the first steps

Each program section below lists three concrete first steps IN THIS REPO. Steps
are ordered; do not skip to step 3 because it is more interesting. Every step
that produces a measurement must predict the number before running (see
`ai-agents-research-methodology`), and every probe of external tool behavior
must follow `ai-agents-empirical-probe-toolkit` (pinned version, foreign
cwd/env, negative control).

### Phase 4: Report and gate

Results go through the normal machinery, not around it: write-ups per
`ai-agents-docs-of-record`, changes through `ai-agents-change-control`, ADR
edits fire the `adr-review` debate gate. A negative result is a result: record
it (the rejected-fix pattern) so the next person does not re-run it.

## Program 1: Verified Governance (ADR-069, PROPOSED)

Thesis (quoting the ADR title verbatim): "The Curated Context Corpus IS the
Product, Orchestration Is Plumbing"
(`.project-toolkit/architecture/ADR-069-context-corpus-is-the-product.md`, status:
proposed, date 2026-05-02). Core frame: no learning between runs; the only thing
that persists is what re-enters the next context window, so the corpus is the
durable competitive surface and everything else is plumbing.

### Why current state of the art fails

- Prompt engineering is folklore: rules ship because they sound right, and
  almost nobody measures whether a rule changes model behavior at all.
- Rules are unmeasured even here: this repo carries more rule files
  under `.claude/rules/` than scenario fixtures under
  `tests/evals/rule-scenarios/`. Run `corpus-counts` for current numbers
  rather than quoting a stored one. Most rules have never had an
  activation baseline.
- Weight tuning is unavailable to a repository: you cannot fine-tune the vendor
  model, so context curation is the only lever, and the field has no shared
  methodology for verifying it.

### This repo's asset

- A large corpus of skill directories, rules, retrospectives, and Serena
  memories. Run `corpus-counts` for current counts.
- Gates that produce inspectable artifacts (verification-based governance):
  every rule violation leaves evidence, so compliance is measurable after the
  fact.
- A working eval harness: `scripts/eval/eval-rule-activation.py` compares
  baseline (no rule) vs description-only vs full-body loading, LLM-judged on
  activation, citation, and behavior scores (1 to 5), with `--dry-run` as the
  zero-spend validation path and ADR-035 exit codes.
- A measured failure baseline to beat: FM-1 (Context Reading Failure) recorded
  95.8% session-start non-compliance in a sampled period
  (`.agents/governance/FAILURE-MODES.md:47`).

### First three steps

1. Wire rule-activation baselines for 3 high-traffic rules that lack fixtures.
   UNVERIFIED: no per-rule traffic measurement exists; as a proxy, pick rules
   cited most often in `.project-toolkit/retrospective/` (grep the rule filename). Write
   scenario JSON files modeled on `tests/evals/rule-scenarios/refactoring.json`,
   dry-run first, predict scores before the paid run.
2. Measure FM-1 compliance rate before and after one deliberate context change
   (for example, moving one rule between description-only and full-body
   loading), using session logs under `.project-toolkit/sessions/` as the compliance
   record. Predict the delta first.
3. Publish the methodology doc: how this repo turns a governance rule into a
   measured, gated, evidenced control. Route it through `adr-generator` or a
   governance doc per `ai-agents-docs-of-record`; it is the publishable unit.

### Falsifiable milestone

You have a result when a controlled eval shows a gated-corpus session
outperforms an ungated session on N pre-registered scenarios with statistically
defensible evidence (pre-declared N, pre-declared success metric, variance
controls per `scripts/eval/variance-control.py`). You have a negative result,
equally worth publishing, if the gated corpus shows no measurable difference:
that would falsify the strong form of ADR-069.

## Program 2: Cross-Harness Abstraction (ADR-072 seam, ADR-068)

### Why current state of the art fails

- Every harness reinvents plugin semantics: Claude Code and Copilot CLI diverge
  on matchers, hook cwd, payload field casing, env anchors, and kill budgets
  (settled contract rows live in `agent-harness-reference`).
- No conformance suites exist: vendors ship docs that were wrong by omission at
  least twice for this repo (plugin-root env vars, payload casing);
  nothing in the ecosystem lets you certify "this plugin behaves identically on
  harness X and Y."

### This repo's asset

- A working multi-target generator: `build/generate_agents.py` emits agent
  trees from `templates/agents/*.shared.md`, and `build/scripts/build_all.py`
  (7 generators) mirrors `.claude/` content into `src/copilot-cli/` and
  `.github/instructions/`, with `--check` as the CI drift gate. Existing target
  trees: `src/vs-code-agents/`, `src/copilot-cli/`, `src/claude/` (manual,
  ADR-036).
- Empirically settled contract tests:
  `tests/build_scripts/test_generate_hooks_runtime_contract.py` pins the hook
  anchoring contract under foreign cwd/env with a negative control, plus
  `scripts/validation/validate_hook_anchoring.py`.
- A settled env-anchor decision memory:
  `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`.
- ADR-068 has real measurements to build on: the ADR-068 measurement recorded 3 of 197
  preToolUse invocations killed by the 2 to 3 second budget, and ~246 ms
  measured Python cold start per shim on Windows with 40 PreToolUse shims.

Label honestly: ADR-072 is accepted (2026-09-12, all five conditions met) but
its frontmatter still says `implemented: false`, so treat the plugin split as
decided, not built. ADR-068 is accepted. Nothing in this program may route around
`ai-agents-change-control`.

### First three steps

1. Formalize the contract table into a versioned spec: extract the
   empirically-verified rows from `agent-harness-reference` and the decision
   memory into one spec file with a version field and per-row evidence links
   (probe retro, memory, or code path). Docs-say rows stay marked docs-say.
2. Build a conformance test runner per harness: parameterize the existing
   runtime-contract tests so the same suite executes against each target tree,
   reporting per-harness pass/fail instead of Claude-only.
3. Third-target dry run: pick one harness this repo does not yet emit for
   (ADR-072 names Codex CLI and Cursor as distribution harnesses), run the
   generator pipeline in `--what-if`/`--check` mode against a prototype
   emission profile, and log every place a hand-edit would have been needed.

### Falsifiable milestone

A new harness target is added with zero hand-edits to generated trees and the
conformance suite green on every harness. The milestone fails, and the
abstraction is falsified, if the third target requires manual patching of
generated output or a contract row that cannot be expressed in the spec.

## Program 3: Self-Improving Loop

Thesis: a correction seen once should become a gated guard, not a memory that
decays. ADR-097 retired every tool-call hook, and ADR-084 retired the `EVENT=`
telemetry emitter and the guard classifier. No producer or consumer exists today.
Live parts: Detect via `reflect`, Log via Serena memories, Graduate via the
skillbook agent, retrieval via `memory` and `memory-search`.

Open step: add a calibration gate to Graduate. Replay a candidate guard against
roughly the last 5 real PRs and show it fires where it should (recipe in
`ai-agents-empirical-probe-toolkit`). Falsified if proposed guards systematically
fail calibration (the earlier guard-replay result: 0 of 35 fix commits) or the loop only proposes
guards a human already hand-coded.

Retired surfaces, the rebuild steps, and the full milestone live in
`references/program3-self-improving-loop.md`. Read it before pitching Program 3.

## Anti-Patterns

| Anti-pattern | Why it fails here | Do instead |
|--------------|-------------------|------------|
| Citing ADR-069 as accepted policy | ADR-069 is PROPOSED. ADR-072 and ADR-068 are accepted, but ADR-072 is not yet implemented | Quote the status line before citing; treat ADR-069 as research direction, not mandate |
| Shipping a detector or guard without replaying it on real history | An M4 threshold could never fire; guards prevented 0/35 of their own fixes | Calibrate against roughly the last 5 real PRs first |
| Trusting vendor docs for harness behavior | Docs were wrong by omission on plugin-root env vars and payload casing | Empirical probe with pinned version and negative control (`ai-agents-empirical-probe-toolkit`) |
| Claiming corpus counts or eval coverage from this file | Counts decay; this file is a snapshot | Run `corpus-counts` and the Phase 1 verification commands |
| Starting a new capability outside the three programs without a gate | AGENTS.md requires the buy-vs-build Quick tier before spec for new capabilities | Run `buy-vs-build-framework`, then `ai-agents-research-methodology` |
| Publishing only positive results | Rejected fixes are load-bearing knowledge (rejected-fix pattern) | Record negative results in a retro or decision memory |

## Scripts

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-research-frontier/scripts/instruments.py" --repo . run corpus-counts
```

`corpus-counts` prints JSON counts of skills, rules, `tests/evals/rule-scenarios`
fixtures, retros (no `INDEX.md`), and `memories_recursive_md` (recursive markdown files under .serena/memories, not the top-level count `corpus-index` returns). `run corpus-index` runs the
failure-archaeology owner script for retro INDEX coverage and failure modes; it
exits 1 while `INDEX.md` omits retros, so a non-zero exit is not a broken skill.
Neither says whether a rule is covered by a fixture. Use `list` to see every row.

## Verification

Before acting on this skill's claims, or after editing it:

- [ ] Ran the Phase 1 re-verify commands; every status and count still matches,
      or this file was updated with new date stamps.
- [ ] Any program step you are about to start has its predicted outcome written
      down before the measurement runs.
- [ ] Everything you plan to cite as settled is Accepted or code-on-disk; all
      PROPOSED and UNVERIFIED labels preserved in your write-up.
- [ ] Your work routes through `ai-agents-change-control` gates (plugin
      version-field, adr-review, drift checks) rather than around them.

## Provenance and Maintenance

Authored 2026-07-03, facts re-verified against the working tree at 42e409325 on 2026-10-31.
Retro-cited SHAs `ddb76e0` and `01e76615a` exist in this clone but are not
reachable from `main`. Clone refs determine whether those objects exist, so
verify ancestry before using `git log`. Prefer `.project-toolkit/retrospective/` and
`.serena/memories/` for the reasoning behind a change, which commit messages
rarely carry.

Sources and re-verification:

- ADR-069 thesis and status: `.project-toolkit/architecture/ADR-069-context-corpus-is-the-product.md` (status: proposed, line 2; title at line 9). Re-verify: `head -12 .project-toolkit/architecture/ADR-069-context-corpus-is-the-product.md`.
- ADR-072 status, review verdict, five conditions, harness list: `.project-toolkit/architecture/ADR-072-jtbd-plugin-architecture.md`. Re-verify: `sed -n '1,25p;119,131p' .project-toolkit/architecture/ADR-072-jtbd-plugin-architecture.md`.
- ADR-068 status and measurements (3/197 kills, ~246 ms cold start, 40 shims): `.project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md`. Re-verify: `sed -n '1,10p' .project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md; grep -n -A1 -e "Three of" -e "246" -e "N=40" .project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md`.
- Rule-activation eval mechanisms, judge dimensions, exit codes: `scripts/eval/eval-rule-activation.py` docstring. Re-verify: `sed -n '1,40p' scripts/eval/eval-rule-activation.py`.
- FM-1 95.8% evidence: `.agents/governance/FAILURE-MODES.md:47`. Re-verify: `grep -n "95.8" .agents/governance/FAILURE-MODES.md`.
- Detect-Log-Graduate and explicit retrieval: the `reflect` skill, `.claude/skills/memory/SKILL.md`, and `.claude/skills/memory-search/SKILL.md`. Re-verify the deleted advisory hooks' absence with `ls .claude/hooks/PreToolUse/`.
- Retired EVENT telemetry and guard classifier: see `references/program3-self-improving-loop.md`.
- Runtime contract test and anchoring validator: `tests/build_scripts/test_generate_hooks_runtime_contract.py`, `scripts/validation/validate_hook_anchoring.py`. Re-verify: `ls tests/build_scripts/test_generate_hooks_runtime_contract.py scripts/validation/validate_hook_anchoring.py`.
- Env-anchor decision memory: `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`. Re-verify: `ls .serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`.
- Counts (skill dirs, rules, retros, memories, scenario fixtures): `corpus-counts`. Volatile; run it, never quote a stored number.
- Incident claims (plugin-root env vars, payload casing, guard replay, M4 threshold, rejected fixes): see `ai-agents-failure-archaeology` for evidence paths; do not re-litigate settled battles.

Unverified in this document (flagged inline): per-rule traffic data, the
automated EVENT consumer pipeline, and the self-improving loop's tracking issues.
Claims about them are cited via on-disk docstrings and ADR references only.

Run the drift check after any edit. `reverify.json` holds the pinned checks.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-research-frontier --require
```
