# Issue #2478 Phase 1: Quality-Gate Signal-to-Noise Baseline

> Phase 1 of the 3-phase Angie Jones principle audit (#2478 -> #2479 -> #2480).
> Produced by a workflow that categorized the last 20 PRs' AI quality-gate agent
> output. Sample PRs: 2501, 2502, 2498, 2482, 2499, 2485, 2487, 2488, 2483, 2484,
> 2476, 2469, 2473, 2337, 2474, 2425, 2467, 2463, 2462, 2461.

## 1. Method, Coverage, and Caveats

**Method.** Categorized every per-agent verdict from a sample of 20 recent PRs
against their quality-gate runs. Each agent run was scored on two counts:
`signalCount` (actionable findings tied to a real defect or required change) and
`noiseCount` (non-actionable output: self-resolved observations, "no action
needed" notes, "cannot verify due to summary context" disclaimers, duplicates of
another agent's finding, and meta-complaints about the agent's own context mode).

**Coverage.** 20 of 20 sampled PRs had usable, rich-comment quality-gate data
(`dataShape=rich-comments`, `ranGate=true` on all 20). Every PR carried all 6
agents (security, qa, analyst, architect, devops, roadmap), giving 120 agent runs
total. This is full coverage of the sample. It is not a full census of all PRs in
the repo; it is a 20-PR window. The signal/noise split rests on the categorization
encoded in the input data, not on a re-read of the raw PR comments.

**Caveats.**

- Signal/noise is a judgment call baked into the input data. Borderline cases were
  not re-adjudicated. A WARN with zero noise examples but a nonzero `noiseCount` (a
  few exist) was counted at face value.
- A dominant noise theme across agents is the `CONTEXT_MODE: summary` disclaimer.
  This is partly a gate-infrastructure artifact (agents got file lists, not full
  diffs), not purely an agent-tuning defect. Phase 2 tuning cannot fix what is
  actually a context-delivery problem; that distinction matters for remediation.
- Small per-PR counts mean ratios are directional, not precise. Treat the ranking
  as robust and the exact percentages as approximate.

## 2. Per-Agent Signal-to-Noise Rollup

| Agent | Runs | Total Signal | Total Noise | Signal Ratio | Dominant Noise Pattern |
|-----------|------|--------------|-------------|--------------|------------------------|
| security | 20 | 2 | 6 | 25% | "Cannot verify X without full diff" disclaimers (summary-context) |
| qa | 20 | 10 | 13 | 43% | Self-resolved "optional cleanup / no action needed" observations |
| analyst | 20 | 8 | 39 | 17% | "Cannot verify from summary context" + duplicates of QA/architect findings + positive "no action required" notes |
| architect | 20 | 13 | 19 | 41% | "Acceptable pattern / good design, no action needed" self-resolved praise |
| devops | 20 | 6 | 27 | 18% | "Cannot verify subprocess/exit-code/parity without full diff" disclaimers |
| roadmap | 20 | 3 | 27 | 10% | "Context mode is summary; cannot verify" + scope notes that self-resolve to "acceptable" |

Aggregate: 42 signal, 131 noise across 120 runs. Repo-wide signal ratio is 24%.
Three of six agents sit below 20%.

## 3. Ranking by Noise (worst first)

1. **analyst** - 39 noise (8 signal, 17% ratio). Highest absolute noise. Inflated
   by duplicating other agents' findings and emitting "no action required"
   confirmations as if they were review output.
2. **devops** - 27 noise (6 signal, 18% ratio). Tied for second on absolute noise.
   Almost entirely "cannot verify without full diff" disclaimers on subprocess
   safety, exit codes, and plugin parity.
3. **roadmap** - 27 noise (3 signal, 10% ratio). Tied on absolute noise but the
   worst signal ratio of any agent and the most WARN-heavy (17 of 20 runs WARN).
   Lowest yield per run.
4. **architect** - 19 noise (13 signal, 41% ratio). High raw noise but the highest
   raw signal too; the noise is mostly self-resolved design praise rather than
   verification disclaimers.
5. **qa** - 13 noise (10 signal, 43% ratio). Best signal ratio. Noise is low-harm
   "optional cleanup" suggestions.
6. **security** - 6 noise (2 signal, 25% ratio). Lowest absolute volume both ways.
   Low noise, but also low signal; it mostly PASSes quietly (17 of 20 PASS).

## 4. Angie Jones Principle Violations (noisiest agents)

Mapping each high-noise agent to the one of Jones's 4 principles (confidence
threshold, actionable examples, CI-awareness, iteration loop) it most violates,
grounded in its noise examples.

**roadmap - most violates Confidence Threshold.**
17 of 20 runs are WARN, and 27 of its outputs are noise against only 3 signal. The
recurring shape is "Context mode is summary; full diff not available for
verification" and "WARN due to summary-only context preventing implementation
verification". The agent fires a WARN it cannot back with a finding, then
frequently self-resolves the same line to "acceptable; no action required" (PR
2483, 2476, 2485). That is emitting below threshold: when it lacks evidence it
should abstain or PASS-with-note, not raise a WARN that carries no actionable
content. The duplicate "PR adds functionality to P2 ... no action required"
confirmations are the same defect: output that clears its own threshold to zero.

**devops - most violates Actionable Examples.**
27 noise, almost all of the form "Cannot verify subprocess command injection safety
for git/gh calls with summary context", "Cannot verify exit code handling follows
ADR-035 contract", "Cannot verify script sync parity ... due to summary context".
None of these name a file, a line, or a concrete fix. Jones's principle is that a
finding must give the developer something to do. A "cannot verify" line gives the
reader nothing actionable; it documents the agent's own blind spot. Where devops
did produce a concrete pointer (PR 2499: `sys.path.insert ... analyze-pr-churn.py:40`)
it was correctly counted toward the small signal pile, which proves the agent can
do it and mostly does not.

**analyst - most violates Iteration Loop (and CI-awareness as a close second).**
39 noise, the highest, driven by two patterns. First, duplication: it repeats QA's
and architect's findings verbatim, explicitly self-labeled "(duplicates QA
finding)", "(duplicate of QA's identical test-file-size finding)" (PR 2487, 2488).
A working iteration loop would suppress a finding already raised by a sibling axis
in the same run; re-emitting it is noise the human must dedupe by hand every time.
Second, it emits positive confirmations as findings: "PR description adequately
explains design intent ... recommendation: None required", "Both scripts follow
ADR-035/ADR-056 ... No action needed". The CI-awareness angle: many of its
disclaimers restate the summary-context limitation that the gate infrastructure
already knows about, instead of adapting output to the context it was given.

## 5. Top Candidates for Phase 2 (#2479)

Three agents carry 93 of the 131 total noise units (71%) and are the clear tuning
targets:

1. **roadmap** - lowest signal ratio (10%), most WARN-inflated (17/20). Highest
   leverage. Fix the confidence threshold so it stops raising evidence-free WARNs.
2. **analyst** - highest absolute noise (39). Add finding-deduplication against
   sibling axes and suppress "no action required" confirmations.
3. **devops** - tied-second noise (27), 18% ratio. Convert "cannot verify"
   disclaimers into either a concrete finding or silence; this overlaps with the
   gate's summary-context delivery, so pair the agent tuning with a context-mode
   fix.

One cross-cutting note for Phase 2: a large share of the noise across roadmap,
devops, analyst, and security is the `CONTEXT_MODE: summary` disclaimer. That is at
least partly an infrastructure limitation, not agent miscalibration. Recommend
re-running the gate with full-diff context (and comment capture) on a fresh sample
before final tuning, so Phase 2 separates "agent emits low-confidence noise" from
"agent was starved of the diff and said so." The 20-PR baseline is enough to rank,
but the disclaimer confound should be controlled before committing to per-agent
prompt patches in Phase 3.
