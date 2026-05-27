# Agent Eval Triage

Per-agent classification for the 23 agents under `.claude/agents/`. Companion to `evals/skill-triage.md` (covers skills). Decides which agents get an A/B spike under `evals/<agent>-agent-spike/`.

## Scope

Every `.claude/agents/*.md` (excluding `CLAUDE.md`, `AGENTS.md`) at 2026-05-27 on `feat/evals-skill-coverage`.

## A/B framing

Agent evals are control-vs-treatment comparisons. The reviewer-asymmetry-spike pattern is the template.

| Comparison | Control | Treatment | Question |
|---|---|---|---|
| Prompt change | `origin/main` agent prompt | HEAD agent prompt | Did the prompt edit help or hurt? |
| Model swap | Current model | Candidate model | Does a cheaper or stronger model match quality? |
| Skill ablation | Agent + skills | Agent without skills | What does the skill chain add? |
| Tool budget | Full tool list | Restricted tools | Does narrowing the toolset cost quality? |

Every spike defaults to **prompt-change A/B** since that is the change shape most often shipped against agent files. Other framings are documented in the spike README so the operator can swap in.

## Classification

Agents differ from skills: every agent is a judgment-bearing role. No utility-skip bucket applies. The split is **already-covered** vs **scaffold-needed**.

| Category | Count | Action |
|---|---|---|
| Already covered | 4 | Cross-referenced below. No new artifact. |
| Scaffold-needed | 19 | New `evals/<agent>-agent-spike/` per agent. |
| **Total** | **23** | |

### Naming

Existing spike dirs (`security-spike`, `reviewer-asymmetry-spike`) use bespoke names. New agent spikes use the `-agent-spike` suffix to disambiguate from skill spikes when the names collide (`adr-generator`, `memory`).

## Already covered (4)

| Agent | Existing spike | Framing |
|---|---|---|
| critic | `evals/reviewer-asymmetry-spike/` | Prompt change (PR #1894 reviewer-asymmetry framing) |
| implementer | `evals/reviewer-asymmetry-spike/` | Prompt change |
| qa | `evals/reviewer-asymmetry-spike/` | Prompt change |
| security | `evals/security-spike/` | Agent-vs-baseline (PLAN-1854 spike) |

Reviewer-asymmetry-spike covers three agents in one corpus; security-spike covers one agent. Both are production-ready and run through `scripts/eval/eval-reviewer-asymmetry.py` and `scripts/eval/eval-agent-vs-baseline.py` respectively.

## Scaffold-needed (19)

Each gets `evals/<agent>-agent-spike/` with `README.md`, `fixtures/README.md`, `fixtures/.gitkeep`. Fixture authoring stays with the operator landing the first live A/B run.

| Agent | Eval target |
|---|---|
| adr-generator | ADR quality: format adherence, completeness, template detection accuracy |
| analyst | Investigation depth, root-cause identification, evidence quality |
| architect | Design coherence, pattern enforcement, boundary discipline |
| backlog-generator | Task quality (sized, actionable, evidence-linked) when generating from project state |
| context-retrieval | Coverage breadth, memory/doc relevance, latency |
| devops | Pipeline correctness, security defaults, cache/concurrency hygiene |
| explainer | PRD clarity, INVEST adherence, ambiguity reduction (junior-reviewer simulation) |
| high-level-advisor | Priority ruthlessness, blind-spot exposure, paralysis resolution |
| independent-thinker | Counter-evidence quality, contrarian-not-contrarian-for-its-own-sake calibration |
| issue-feature-review | Cost/value verdict accuracy, unknown-flagging recall |
| memory | Memory write atomicity, retrieval relevance, cross-session continuity |
| milestone-planner | Milestone decomposition quality, dependency capture, AC clarity |
| orchestrator | Routing correctness, handoff fidelity, synthesis quality |
| quality-auditor | Grade accuracy across domains, gap-tracking recall |
| retrospective | Pattern extraction quality, atomicity scoring, learning-matrix coverage |
| roadmap | Outcome-focus, RICE/KANO application, strategic-drift detection |
| skillbook | Skill quality gates, dedup detection, atomicity rejection |
| spec-generator | EARS adherence, three-tier completeness, traceability |
| task-decomposer | Atomicity, AC presence, DoD clarity, dependency sequencing |

## Suggested A/B fixture distribution (per agent)

Baseline target per spike (operator-tunable):

- **6-10 fixtures total**
- **Verdict bands**: 3-5 controlled labels appropriate to the agent's output
- **Agent-discriminating ≥30%**: cases where the naive baseline cannot answer correctly without the agent's prompt-encoded knowledge (REQ-004 AC-5)
- **Trials per fixture per condition**: 10 (binomial design, two-tailed Fisher's exact at p < 0.05; see reviewer-asymmetry-spike methodology)

## Cross-references

- `evals/skill-triage.md`. Companion classification for skills.
- `evals/reviewer-asymmetry-spike/README.md`. A/B prompt-change template.
- `evals/security-spike/README.md`. Agent-vs-baseline template.
- `scripts/eval/eval-reviewer-asymmetry.py`. Reviewer-asymmetry runner.
- `scripts/eval/eval-agent-vs-baseline.py`. Agent-vs-baseline runner.
- `.serena/memories/skills/triage-eval-2026-05-27-full-coverage`. Skill triage memory.
- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md). Prompt behavioral evaluation.
- REQ-004 / DESIGN-004 / [PLAN-1854](.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md). Agent-vs-baseline harness origin.
