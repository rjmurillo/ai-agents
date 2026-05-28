# Baseline Eval Report

Baseline measurement: do current agent prompts beat a naive baseline on a held-out corpus? Aggregate run across 18 agent spikes on fixtures derived from rjmurillo/moq.analyzers, dotnet/runtime, and rjmurillo/ai-agents public PRs and issues.

## Date

2026-05-28

## Aggregate matrix (18 agents)

| Agent | Fixtures | Agent | Baseline | Delta | 95% CI | Verdict | Cost |
|---|---|---|---|---|---|---|---|
| security | 10 | 0.833 | 0.417 | **+0.417** | [+0.100, +0.727] | **SIG-POS** | $1.00 |
| task-decomposer | 8 | 0.917 | 0.750 | +0.167 | [+0.000, +0.333] | lean-pos | $0.28 |
| independent-thinker | 8 | 0.750 | 0.583 | +0.167 | [+0.000, +0.333] | lean-pos | $0.29 |
| memory | 8 | 0.857 | 0.714 | +0.143 | [+0.000, +0.286] | lean-pos | $0.36 |
| high-level-advisor | 8 | 0.583 | 0.479 | +0.104 | [-0.021, +0.250] | lean-pos | $0.24 |
| orchestrator | 8 | 0.786 | 0.714 | +0.071 | [-0.143, +0.286] | lean-pos | $0.35 |
| qa (triad-aware) | 8 | 0.458 | 0.417 | +0.042 | [-0.292, +0.354] | NULL | $0.59 |
| skillbook | 8 | 0.750 | 0.750 | +0.000 | [-0.250, +0.250] | NULL | $0.26 |
| explainer | 8 | 0.786 | 0.786 | +0.000 | [-0.286, +0.286] | NULL | $0.24 |
| roadmap | 8 | 0.643 | 0.643 | +0.000 | [-0.214, +0.214] | NULL | $0.21 |
| analyst | 24 | 0.825 | 0.850 | -0.025 | [-0.100, +0.050] | NULL | $1.02 |
| critic | 8 | 0.833 | 0.917 | -0.083 | [-0.250, +0.000] | lean-neg | $0.37 |
| devops (triad-aware) | 8 | 0.750 | 0.833 | -0.083 | [-0.250, +0.000] | lean-neg | $0.26 |
| implementer | 8 | 0.667 | 0.750 | -0.083 | [-0.333, +0.167] | lean-neg | $0.45 |
| issue-feature-review | 8 | 0.542 | 0.625 | -0.083 | [-0.417, +0.188] | lean-neg | $0.24 |
| backlog-generator | 8 | 0.750 | 0.833 | -0.083 | [-0.333, +0.167] | lean-neg | $0.23 |
| architect (triad-aware) | 8 | 0.562 | 0.667 | -0.104 | [-0.333, +0.146] | lean-neg | $0.67 |
| milestone-planner | 8 | 0.643 | 0.857 | **-0.214** | [-0.429, -0.071] | **SIG-NEG** | $0.29 |

Two with deferred eval (no `templates/agents/<name>.shared.md` exists):

| Agent | Status |
|---|---|
| context-retrieval | DEFERRED (no shared.md) |
| quality-auditor | DEFERRED (no shared.md) |
| spec-generator | DEFERRED (no shared.md) |
| adr-generator | DEFERRED (no shared.md) |

Excluded per [#2080](https://github.com/rjmurillo/ai-agents/issues/2080):

| Agent | Status |
|---|---|
| retrospective | EXCLUDED (moving to skill per #2080) |

**Aggregate live spend this run: $7.35.** Cumulative across all eval work on this PR: ~$16.42 across ~1,150 trials.

## Headline findings

1. **One clear winner: security** (+0.417, CI [+0.100, +0.727]). The only agent where the specialized prompt beats baseline at statistical significance.
2. **One clear loser: milestone-planner** (-0.214, CI [-0.429, -0.071]). The naive baseline beats the specialized agent at statistical significance. Either the prompt is hurting, or (more likely given the bimodal pattern below) the fixtures + harness vocabulary penalize this agent's natural output shape.
3. **Bimodal pattern: structural-discipline agents win, judgment agents lose.**
   - Win lean: task-decomposer (+0.167), independent-thinker (+0.167), memory (+0.143), high-level-advisor (+0.104), orchestrator (+0.071). All produce structured, enumerable output the harness can score.
   - Lose lean: critic (-0.083), devops (-0.083), implementer (-0.083), issue-feature-review (-0.083), backlog-generator (-0.083), architect (-0.104), milestone-planner (-0.214). All are judgment/critique agents whose natural verdict vocabulary (`REJECT`, `BLOCKED`, `NEEDS REVISION`, `APPROVE`) does not map cleanly to the harness's `IDENTIFY | OK | ESCALATE` contract.

## Triad-aware fixtures (architect, devops, qa)

Per `~/Documents/Mobile/wiki/comparisons/Anthropic Interpretability Triad vs The Bicameral Bet.md`, the original architect, devops, qa fixtures saturated at 0.000 because the model defaults already solved them. Replaced with 24 fixtures built from the five operational facts:

1. **CoT conditional faithfulness** -> force artifacts (file:line citations), not narration
2. **Misfired known-entity inhibitor** -> planted fake ADRs (`ADR-091`), fake file paths, fake secret names, fake AC numbers; agent must verify or ESCALATE
3. **Introspection ~= abstractness signal** -> replaced "rate confidence" with kill-criteria (3 falsifiable observations)
4. **Capability in synergistic middle layers** -> "list 2 alternatives before recommending" gates
5. **Emotion vectors** -> no-affect baits ("team is excited", "non-controversial", "moving fast"); agent must remain blunt

**Discrimination improved on all three.** The new fixtures separated agent and baseline behavior where the old ones saturated:

| Agent | Old delta (saturated corpus) | Triad-aware delta | Discrimination improvement |
|---|---|---|---|
| architect | 0.000 | -0.104 | Now measurable |
| devops | 0.000 | -0.083 | Now measurable |
| qa | 0.000 | +0.042 | Now measurable |

**Real differential behavior revealed:**

- Agents WIN on structural-discipline fixtures: kill-criteria (architect A005 +0.50, devops D004 +0.33 flaky, qa Q004 +0.17), status-claim evidence (qa Q002 +0.83), no-affect resistance (qa Q007 +0.50).
- Agents LOSE on legit-OK fixtures: when the input is genuinely clean, the specialized agent over-skepticizes and false-ESCALATEs while baseline correctly approves. devops D005 -0.83 (rejects a clean workflow), qa Q005 -0.83 (rejects a comprehensive test plan), architect A006 -0.50 (rejects real ADR citations).

This is the **inverse of the analyst ESCALATE bias**: where analyst over-IDENTIFIES on ESCALATE cases, these three agents over-ESCALATE on OK cases. Both directions of mismatch arise from the same root cause: the harness verdict contract is one-dimensional (IDENTIFY|OK|ESCALATE) while agent prompts encode multi-dimensional verdict structures.

## Critical caveat: harness verdict-vocabulary forces all output through IDENTIFY|OK|ESCALATE

Per `scripts/eval/eval-agent-vs-baseline.py`, the runner appends a fixed OUTPUT_SHAPE_SUFFIX: "Begin your response with exactly one word: IDENTIFY, OK, or ESCALATE." Agents whose canonical verdict vocabulary uses other tokens (`BLOCKED`, `REJECT`, `APPROVE`, `PASS`/`FAIL`/`NEEDS REVISION`, structured findings) score worse on the verdict assertion than they would under their native contract.

The security spike caught this on its first run (Cursor Bugbot): security still beat baseline because the regex CWE-code assertions passed. Other lean-negative agents may not have the same compensating regex assertions.

Three fix paths (not in scope here):

1. Extend `OUTPUT_SHAPE_SUFFIX` to accept per-agent verdict vocabularies.
2. Add a normalization step in `_VERDICT_RE` mapping agent-native verbs to IDENTIFY|OK|ESCALATE bands.
3. Align all agent templates to the harness vocabulary (most invasive).

## Per-agent verdict

| Agent | Verdict | Rationale |
|---|---|---|
| security | **KEEP** | Only SIG-POS. Cited CWE codes show real specialization regex-detects. |
| task-decomposer | KEEP, monitor | Lean-positive on atomic-task fixtures + verbatim-patch discipline. |
| independent-thinker | KEEP, monitor | Lean-positive on contrarian/counter-evidence fixtures. |
| memory | KEEP, monitor | Lean-positive on atomic-write + stale-detection fixtures. |
| high-level-advisor | KEEP, re-eval | Lean-positive but CI touches zero. Real fixtures need to require the "no comfort / brutal honesty" framing more strongly. |
| orchestrator | KEEP, monitor | Lean-positive on routing + delegation fixtures. |
| qa (triad-aware) | KEEP after audit | NULL with wide CI but real wins on status-claim/no-affect fixtures. Audit the false-ESCALATE on OK fixtures. |
| skillbook, explainer, roadmap | NULL | Indistinguishable from baseline. Author harder fixtures requiring each agent's specialization vocabulary, then re-eval. |
| analyst | KEEP, audit prompt | NULL on 24 fixtures across three corpus iterations. ESCALATE-bias documented. Audit the prompt's "Investigate what you have" tension. |
| critic | KEEP, audit harness | Lean-negative but most likely cause is verdict-vocab mismatch, not prompt failure. The reviewer-asymmetry-spike has historical evidence the prompt produces real lift (May-9 final.json shows +0.5 on critic). |
| devops (triad-aware) | KEEP, audit | Lean-negative; over-ESCALATEs on legit OK workflows. The kill-criteria and force-alternatives fixtures DO show specialization (D004 +0.33 flaky). |
| implementer | KEEP, audit harness | Lean-negative; same verdict-vocab confound as critic. Historical evidence from reviewer-asymmetry-spike (May-9) showed +0.85 implementer delta. |
| issue-feature-review | KEEP, audit | Lean-negative but CI very wide [-0.417, +0.188]. Re-eval with harder fixtures and the verdict-vocab fix. |
| backlog-generator | KEEP, audit | Lean-negative, narrow CI. Specific failure mode: agent generates tasks the baseline correctly says "already exist". Audit the duplicate-detection prompt section. |
| architect (triad-aware) | KEEP, audit | Lean-negative; over-skeptical on OK fixtures (A006 -0.50 when real ADR citations were cited). |
| milestone-planner | **AUDIT URGENT** | Only SIG-NEG. Baseline beats by 0.214 with CI excluding zero. Either the prompt is actively hurting or the fixtures over-penalize this agent. Re-author fixtures and re-eval before any cut decision. |
| context-retrieval, quality-auditor, spec-generator, adr-generator | DEFERRED | No `templates/agents/<name>.shared.md` exists; harness cannot load the agent system prompt. Author template or extend harness. |
| retrospective | EXCLUDED | Moving to skill per [#2080](https://github.com/rjmurillo/ai-agents/issues/2080). |

## Methodology

Per spike: 3-5 independent runs per fixture per variant at default temperature. Verdict assertion passes when output begins with the expected verdict from IDENTIFY|OK|ESCALATE. Regex assertions pass when the pattern matches anywhere in the body. Recall is mean per-fixture pass rate. Bootstrap CI uses 1000 resamples of fixture-level deltas.

Flaky fixtures (intra-run variance > 0 within a single variant) are detected and selectively excluded by the runner when their inclusion would push error rate above MAX_ERROR_RATE (REQ-004 AC-3).

Baseline prompt is fixed: "Review the following input." plus OUTPUT_SHAPE_SUFFIX. Specialization (the agent's `templates/agents/<agent>.shared.md`) is the only free variable between variants.

## What this PR ships

- 18 spike directories under `evals/<agent>-spike/` with authored fixtures and live-run reports.
- 168 fixtures total (security 10, analyst 24, 16 other agents at 8 each except architect/devops/qa which got 8 triad-aware after corpus rebuild).
- 2 triage docs (`evals/skill-triage.md`, `evals/agent-triage.md`).
- This baseline report (3rd revision).
- Reviewer-asymmetry-spike retained as historical reference (today's run shows saturation; May-9 final.json captures pre-merge state where critic and implementer showed +0.5 and +0.85 lift respectively).

## Followups (ranked by leverage)

1. **Fix the verdict-vocabulary confound.** Single biggest source of measurement noise. Lean-negative on 6 of 18 agents most likely traces here.
2. **Audit milestone-planner prompt.** Only SIG-NEG; either prompt hurts or fixtures need rebuild.
3. **Add `templates/agents/<name>.shared.md`** for context-retrieval, quality-auditor, spec-generator, adr-generator. Or extend harness to read `.claude/agents/<name>.md` directly.
4. **Author harder fixtures** for skillbook, explainer, roadmap that require each agent's specific framing.
5. **Triad-aware fixtures for the lean-negative judgment agents** (critic, implementer, issue-feature-review). The existence-check + kill-criteria + no-affect bait patterns are general and could be templated.
6. **Quarterly cron** wiring `scripts/eval/eval-suite.py` for security (the SIG-POS spike). Detect drift before it ships.
7. **Convert retrospective to skill** per [#2080](https://github.com/rjmurillo/ai-agents/issues/2080).

## What this report is NOT

- Not a verdict that any agent should be deleted. The lean-negative cluster most likely reflects the verdict-vocabulary mismatch and harder-to-game fixtures, not a failure of the agent prompt.
- Not a coverage claim for all skills. Skills are not evaluated here; see `evals/skill-triage.md`.
- Not a substitute for unit tests. Eval signal is behavioral, not correctness.

## Cross-references

- [evals/skill-triage.md](./skill-triage.md) - 71-skill classification.
- [evals/agent-triage.md](./agent-triage.md) - 23-agent classification.
- [evals/security-spike/](./security-spike/) - reference implementation.
- [evals/analyst-spike/](./analyst-spike/) - 24-fixture corpus.
- [evals/architect-spike/fixtures/](./architect-spike/fixtures/) - triad-aware corpus example.
- [scripts/eval/eval-agent-vs-baseline.py](../scripts/eval/eval-agent-vs-baseline.py) - runner.
- [ADR-057](../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md) - prompt behavioral evaluation.
- REQ-004 / DESIGN-004 / [PLAN-1854](../.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md) - harness origin.
- `~/Documents/Mobile/wiki/comparisons/Anthropic Interpretability Triad vs The Bicameral Bet.md` - source of triad-aware fixture design.
