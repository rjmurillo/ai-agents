<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: .agents/governance/FAILURE-MODES.md, .project-toolkit/architecture/ADR-097-zero-tool-use-hooks.md -->

# Program 3: Self-Improving Loop (detail)

Facts checked at 42e409325 on 2026-10-31. Issue #1345 is the origin.

## Why state of the art fails

- Agent memories decay. Observations pile up and nothing promotes them.
- Corrections do not become enforcement. The industry pattern stops at writing corrections to memory, which is advisory. FM-1 recorded 95.8% non-compliance (`.agents/governance/FAILURE-MODES.md:47`) while gates held.

## Live parts

- Detect via the `reflect` skill. Log via Serena observation memories. Graduate via the skillbook agent.
- Retrieve corrections and topical memories explicitly through `memory` or `memory-search`. The advisory correction-applier and topical-memory-injection hooks were deleted (issue #3184).
- `memory-reflexion` (ADR-063) extracts episodes. ADR-089 removed its derived causal graph for having no reader.

## Retired surfaces

- ADR-097 (`.project-toolkit/architecture/ADR-097-zero-tool-use-hooks.md`) retired all tool-call hooks and the Copilot dispatcher in f79e70c01 (2026-08-19, #5172).
- ADR-084 (issue #5154) deleted `push_guard_base.py`, which wrote an `EVENT={...}` line to stderr on each block. It also deleted every guard built on it and the skill that classified guards as Budding, Growing, Mature, Proficient, Inert, or Harmful.
- No emitter and no consumer of that schema exists. The `EVENT=` consumer pipeline was UNVERIFIED even before the deletion.
- Cross-project supplementary recall is gone: the memory server behind it was decommissioned in #5574.

## Not built

- The Graduate step has no calibration gate. #1989 M4 shipped a threshold that could never fire. The #1887 Phase-6 audit found its own guards would have prevented 0 of 35 fix commits.

## First steps

1. Rebuild telemetry only on a guard that exists at the time: a new emitter, a scheduled aggregator, and a record of where events persist. The retired design is reference, not a pipeline to close.
2. Add the calibration gate. Replay a candidate guard against roughly the last 5 real PRs. Show it fires where it should and stays silent where it should (`ai-agents-empirical-probe-toolkit`).
3. Prototype auto-proposal. When one correction memory surfaces more than N times, emit a draft guard (code plus calibration fixture) as a PR for human review. Never auto-merge. Change classes stay under `ai-agents-change-control`.

## Falsifiable milestone

A correction observed once auto-proposes a guard that survives the calibration replay and ships through review. Falsified if proposed guards systematically fail calibration, or if the loop only proposes guards a human already hand-coded.
