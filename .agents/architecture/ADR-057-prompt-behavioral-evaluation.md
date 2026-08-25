---
id: ADR-057
status: accepted
date: 2026-07-22
decision-makers: [architect, user]
supersedes: []
superseded-by: null
explainer: null
implemented: true
consulted:
- qa
- security
- critic
informed:
- implementer
- analyst
- devops
---

# ADR-057: Prompt Behavioral Evaluation Methodology

## Context and Problem Statement

ADR-023 introduced structural validation for quality gate prompts using Pester tests. Structural tests verify required sections, formatting, and terminology consistency. They run in seconds and produce deterministic results.

Structural tests cannot detect behavioral regressions. A prompt can pass all 84 structural tests while producing incorrect LLM verdicts. ADR-023 acknowledged this limitation explicitly in its "Out of Scope" section:

> **Runtime AI behavior validation** - Tests cannot verify AI interprets prompts correctly

Issue #1686 demonstrated this gap. A prompt change to `.claude/commands/research.md` added budget thresholds, fallback rules, and stop conditions. The first draft regressed behavior by 20 percentage points. Ambiguous budget wording caused the LLM to stop too early. Structural tests would not have caught this. Only scenario-based evaluation against the LLM detected the regression before merge.

Issue #1688 requested formalizing this evaluation approach into a reusable methodology.

## Decision Drivers

1. **Behavioral correctness**: Prompt changes that alter instructions, thresholds, or decision logic need validation beyond structure
2. **Regression prevention**: Changes must not degrade existing behavior without explicit justification
3. **Reproducibility**: Evaluations must be versioned and rerunnable against future prompt or model changes
4. **Model drift detection**: LLM interpretation can shift across model versions without any prompt change
5. **Cost awareness**: Behavioral evals invoke the LLM and cost time and API tokens

## Prior Art Investigation

### What Currently Exists

- **Structure/pattern being changed**: ADR-023 Pester structural tests (84 tests, ~4 seconds)
- **When introduced**: ADR-023, 2025-12-26
- **Original author and context**: Architect and user, motivated by Issue #357 (false CRITICAL_FAIL on DOCS-only PRs)

### Historical Rationale

- **Why was it built this way?** Structural validation was chosen for speed, determinism, and low infrastructure cost. Runtime AI testing was explicitly deferred due to API costs, nondeterminism, and infrastructure complexity.
- **What alternatives were considered?** Manual testing (rejected: slow, error-prone), runtime AI response tests (deferred: expensive, nondeterministic)
- **What constraints drove the design?** CI integration speed (<10 seconds), zero API cost, deterministic pass/fail

### Why Change Now

- **Has the original problem changed?** Yes. Issue #1686 proved that behavioral regressions occur in practice and that structural tests miss them.
- **Is there a better solution now?** Yes. Scenario-based evaluation with before/after comparison provides a lightweight behavioral validation pattern without requiring full golden corpus infrastructure.
- **What are the risks of change?** Moderate. Behavioral evals are probabilistic and cost API tokens. They supplement structural tests, not replace them.

## Decision

Adopt scenario-based LLM evaluation as the standard method for validating behavioral correctness of prompt changes. This methodology is documented in `.agents/testing/prompt-eval-methodology.md` and is now elevated to architectural policy.

### Scope: Files Requiring Behavioral Evaluation

| Category | Path Patterns |
|----------|---------------|
| Commands | `.claude/commands/*.md` |
| Quality gate prompts | `.github/prompts/*.md` |
| Security prompts | `.agents/security/prompts/*.md` |
| Agent definitions (Claude Code) | `.claude/agents/*.md` |
| Agent definitions (published) | `src/claude/*.md`, `src/copilot-cli/*.md`, `src/vs-code-agents/*.md` |
| Skill definitions | `.claude/skills/*/SKILL.md` |

Excluded from behavioral eval: `CLAUDE.md`, `README.md`, `INDEX.md`, `AGENTS.md`, and `.template.` files.

### Core Pattern

Each evaluation consists of:

1. **Scenarios**: Named input conditions with expected verdicts and reason-contains assertions
2. **Runner**: Invokes the LLM with prompt text plus scenario input, parses the verdict
3. **Before/after comparison**: Runs all scenarios against the prompt before and after the change, computes score delta

### Acceptance Gate

The gate blocks regressions. It does not mandate an improvement on every edit. A prompt change passes behavioral evaluation when these criteria hold:

1. `after_score >= before_score` (no regression on existing scenarios)
2. No scenario flips from pass to fail. Every pass-to-fail flip is recorded in `regressions` and blocks the gate automatically; the gate has no mechanism to accept a "justified" regression. Where the gate runs as a blocking CI leg (currently the `/spec` eval in `.github/workflows/slash-command-quality.yml`), a deliberate behavior change normally lands by updating the scenario expectations alongside the prompt in the same change, so the new expectations move with the intended behavior and the gate passes without a bypass. Only accepting a regression against unchanged expectations requires a human override (admin merge) with the rationale documented in the PR. For prompt files with no blocking CI leg, the gate is advisory and PR review carries the same judgment (see Amendment 2026-07-22).
3. Flakiness on any scenario stays at or below the 40% block threshold.

A change that targets a failing scenario SHOULD move it from fail to pass. This is recorded as `has_improvement` and surfaced in the gate output, but it is not a hard pass requirement (see the 2026-06-01 relaxation note below).

#### Acceptance Gate Relaxation (2026-06-01, Issue #2197)

The original gate required `has_improvement` (at least one fail-to-pass flip, or `before_score == 1.0`) as a hard pass condition. This structurally blocked any legitimate change to a prompt whose base ref already had a failing scenario. Example: a documentation-consistency edit to `.claude/commands/spec.md` introduces no behavioral change and no regression, but pre-existing scenarios D13 and D14 fail on `main` (`before_score` 5/7 < 1.0). With zero fail-to-pass flips, `has_improvement` was false and the gate returned FAIL even though the change regressed nothing.

That outcome contradicts the gate's stated purpose: regression prevention (Decision Driver 2), not a mandate that every edit improve a score. The criterion "any scenario the change targets moves from fail to pass" was always conditional on the change targeting a scenario; it was never meant to apply to changes that target no scenario.

Relaxation: `has_improvement` is dropped as a hard pass requirement in `eval-prompt-change.py acceptance_gate()`. The gate now passes when `no_regression AND no_unexplained_regressions AND no_high_flakiness` hold (plus the security-critical 100%-pass requirement when applicable). `has_improvement` is still computed and reported in the gate criteria for visibility.

Regression blocking is preserved. Every pass-to-fail flip records the scenario in `regressions`, so `no_unexplained_regressions` fails and the gate returns FAIL. This holds even when an offsetting improvement keeps `after_score` flat (so `no_regression` stays true): the `regressions` list, not the score delta, is the authoritative block signal. The security-critical 100%-pass requirement is untouched: a security-critical run below 100% pass rate still blocks regardless of improvement state.

#### Security-Critical Prompt Tier

Prompts in the security domain (security agent, quality gate security prompts) require a stricter gate:

- MUST: Run each scenario a minimum of 5 times. Enforced by `--security-critical` flag in eval-prompt-change.py.
- MUST: Require 100% pass rate across all runs. Enforced by acceptance gate in eval-prompt-change.py.
- SHOULD: Scenario files reviewed by a CODEOWNERS-designated reviewer before merge. Enforced by code review (not automated).

#### Flakiness Protocol

For non-security prompts, when a scenario produces inconsistent results across runs:

- MUST: Run the scenario 3 times minimum. Enforced by `DEFAULT_RUNS = 3` in eval-prompt-change.py.
- MUST: A scenario passes if it succeeds in at least 2 of 3 runs. Enforced by `(runs * 2) // 3` threshold in run_scenario_multi().
- MUST: If flakiness rate exceeds 40% on any scenario, the gate fails. Enforced by `FLAKINESS_BLOCK_THRESHOLD = 0.4` in acceptance_gate().
- SHOULD: Document the flaky scenario in the PR with observed pass/fail ratio. Enforced by code review.

### When to Run

| Trigger | Level | Enforced By | Rationale |
|---------|-------|-------------|-----------|
| Prompt change alters instructions, thresholds, or decision logic | MUST (obligation to run) | Enforcement advisory: run eval-prompt-change.py before PR; PR review verifies. No commit-time auto-block; the `/spec` CI leg is the one blocking exception (see Amendment 2026-07-22) | Direct behavioral impact |
| Prompt change alters text structure only | N/A | N/A (structural tests suffice) | No behavioral risk |
| Ambiguous (rewording that may shift semantics) | MUST (obligation to run) | Enforcement advisory: run eval-prompt-change.py before PR; PR review verifies. No commit-time auto-block; the `/spec` CI leg is the one blocking exception (see Amendment 2026-07-22) | When in doubt, treat as behavioral |
| Monthly for prompts under active iteration | SHOULD | Not automated (manual cadence) | Detect model drift |
| After Anthropic model version bump | SHOULD | Not automated (manual trigger) | Catch interpretation shifts |

### Scenario Adequacy

Minimum requirements for scenario coverage:

- MUST: A prompt with 0 scenarios does not satisfy the gate. Enforced by load_scenarios() which rejects empty scenario files.
- SHOULD: At least one scenario per decision branch the prompt change introduces or modifies. Enforced by code review.
- SHOULD: At least one regression scenario for existing behavior the change could affect. Enforced by code review.
- SHOULD: Scenario coverage reviewed as part of the PR review process. Enforced by code review.

### Cost Expectations

Estimated cost per eval cycle (based on Issue #1686 experience):

- 5 scenarios, 2 runs each (before + after): ~10 LLM invocations
- ~2,000-5,000 tokens per invocation (prompt + scenario input + response)
- Total: ~20,000-50,000 tokens per eval cycle
- Time: 2-5 minutes depending on model latency

These estimates scale linearly with scenario count. Track actual costs per eval run. If cumulative monthly cost exceeds $50 or cumulative time exceeds 2 hours, reassess methodology scope.

### Scenario Storage

Store scenarios under version control alongside the prompt they test. Locations:

| Prompt Type | Scenario Location |
|-------------|-------------------|
| Security benchmarks | `.agents/security/benchmarks/` |
| Other prompt evals | `tests/evals/` |

### Relationship to Structural Tests

Behavioral evals complement structural tests. They do not replace them.

| Need | Use | Speed | Determinism |
|------|-----|-------|-------------|
| Required sections, format, terminology | Structural tests (ADR-023) | Fast (seconds) | Deterministic |
| LLM interpretation, verdict correctness, regression proof | Behavioral evals (this ADR) | Slow (minutes, API cost) | Probabilistic |

A change that alters both structure and behavior needs both test types.

## Considered Options

### Option 1: Manual Testing (Status Quo for Behavioral Changes)

Test prompt changes by manually running against sample inputs and inspecting LLM responses.

| Aspect | Assessment |
|--------|------------|
| Pros | No infrastructure, flexible |
| Cons | Not repeatable, no regression baseline, no version control, slow |
| Why not chosen | Issue #1686 showed manual testing missed a 20pp regression |

### Option 2: Golden Corpus Testing

Maintain a large corpus of known-correct input/output pairs. Compare LLM responses against the corpus.

| Aspect | Assessment |
|--------|------------|
| Pros | High coverage, strong regression detection |
| Cons | Expensive to build and maintain, brittle to model changes, high API cost per run |
| Why not chosen | Premature for current scale. Scenario-based evals require fewer scenarios to start and lower maintenance burden. No empirical comparison exists to quantify the coverage difference. Can evolve toward golden corpus if scale demands it. |

### Option 3: Scenario-Based LLM Evaluation (Chosen)

Define targeted scenarios with expected verdicts. Run before/after comparison on each prompt change.

| Aspect | Assessment |
|--------|------------|
| Pros | Lightweight, versioned, rerunnable, caught real regression (Issue #1686) |
| Cons | Probabilistic results, API cost, limited to defined scenarios |
| Why chosen | Proven effective on Issue #1686 (+20pp improvement via eval-driven iteration). Right balance of cost and coverage for current scale. |

## Consequences

### Positive

- Behavioral regressions are caught before merge where the eval runs as a blocking CI leg (currently `/spec`); for other in-scope prompt files the eval is advisory at PR review (see Amendment 2026-07-22)
- Evaluation results are versioned and reproducible
- Model drift is detectable through scheduled reruns
- Completes the testing story that ADR-023 left open

### Negative

- Behavioral evals add minutes and API cost to prompt change validation
- Probabilistic results may produce flaky outcomes on edge-case scenarios
- Scenario design requires understanding of expected LLM behavior, which adds author burden

### Neutral

- Does not affect prompts that only change structure (ADR-023 still covers those)
- Runner implementation is not prescribed. Teams can use Task tool subagents or direct API calls.
- Eval results should record the model ID used (e.g., `claude-sonnet-4-6`) to enable drift detection across model versions.

## Confirmation

### Enforced (automated gates)

These gates run inside `eval-prompt-change.py`. They fire whenever the eval runner is invoked: advisorily when a contributor runs it before a PR, and as a blocking check when the `/spec` CI leg (`.github/workflows/slash-command-quality.yml`) invokes it on a same-repo PR that changes the `/spec` command, its scenario set, or the eval runner. That leg always evaluates the `/spec` command behavior only; a change to the scenario set or the runner triggers a re-evaluation of that same command. No commit-time hook auto-invokes them (see Amendment 2026-07-22).

| Rule | Enforced By | Mechanism |
|------|-------------|-----------|
| Scenario file must contain >= 1 scenario | eval-prompt-change.py load_scenarios() | RuntimeError on empty file |
| after_score >= before_score (no regression) | eval-prompt-change.py acceptance_gate() | Gate returns FAIL |
| No scenario flips pass to fail | eval-prompt-change.py acceptance_gate() | Gate returns FAIL |
| Flakiness > 40% blocks gate | eval-prompt-change.py acceptance_gate() | FLAKINESS_BLOCK_THRESHOLD = 0.4 |
| Security prompts: 5 runs, 100% pass | eval-prompt-change.py --security-critical | Overrides runs, requires 100% pass_rate |
| Non-security: 3 runs, 2/3 pass | eval-prompt-change.py DEFAULT_RUNS | (runs * 2) // 3 threshold |
| --runs >= 1 | eval-prompt-change.py _parse_args() | parser.error on invalid value |
| API keys from environment variables | _anthropic_api.py load_api_key() | Reads env var, never hardcoded |

### Not enforced (code review only)

| Rule | Why Not Automated | Mitigation |
|------|-------------------|------------|
| Prompt/skill/agent changes require eval evidence | No commit-time hook (deleted in #3184); one CI leg blocks for `spec.md` only, broader CI automation deferred (below) | PR reviewer checks for eval evidence; advisory except the `/spec` CI leg |
| >= 1 scenario per decision branch | Requires understanding prompt semantics | PR reviewer checks scenario adequacy |
| >= 1 regression scenario | Same | PR reviewer checks |
| Monthly drift reruns | Scheduling concern, not commit-time | Manual cadence, future cron job |
| Model-bump reruns | No model version detection mechanism | Manual trigger after model updates |
| Cost ceiling ($50/month) | No cost aggregation across runs | Track manually, reassess if exceeded |
| Flaky scenario documentation in PR | Free-text in PR description | PR reviewer checks |

### Enforcement Path

- **Current**: No commit-time gate. The deleted PreToolUse hook that nominally blocked commits (`invoke_prompt_eval_gate.py`) was inert (it printed `{"decision":"deny"}` with exit 0, a payload the Claude Code harness ignores) and was removed in #3184. One CI leg does block: `.github/workflows/slash-command-quality.yml` runs the `eval-prompt-change.py` acceptance gate against `.claude/commands/spec.md` on same-repo PRs that change the `/spec` command, its scenario set (`tests/evals/spec-scenarios.json`), or the eval runner, and fails the check on regression. That leg covers `spec.md` only. For every other prompt, skill, and agent file the eval evidence requirement is advisory, verified at PR review. The `eval-prompt-change.py` acceptance gate enforces regression, flakiness, and security-critical rules only when it is run.
- **Not automated**: Scenario adequacy, monthly cadence, cost tracking. These require human judgment or scheduling infrastructure not yet built.
- **Future**: Broader CI automation of eval runs, beyond the `/spec` leg that already ships. Deferred until the eval runner stabilizes and the cost model is validated.

## Amendment 2026-07-22 (Issue #3185): eval enforcement is advisory, not commit-blocking

The original ADR claimed a deleted Claude Code PreToolUse hook (`invoke_prompt_eval_gate.py`) blocked commits lacking eval evidence. That claim was false from the start: the hook emitted a `{"decision":"deny"}` payload with exit 0, which the harness ignores (the same bug class fixed in the historical `invoke_security_commit_gate.py`, Issue #2521). The hook never blocked a commit. Measured drain: from 2026-06-01, 108 commits touched eval-scoped prompt files while 1 commit added eval evidence.

#3184 deleted the inert hook. This amendment corrects the resulting torn references (the Acceptance Gate note, the "When to Run" and "Confirmation" tables, the Consequences list, the Enforcement Path, and the dependent-components table) so the ADR no longer points at a deleted file or asserts an automated block that never existed, and it scopes the one real block (the `/spec` CI leg) precisely.

Decision (Deliverable B of #3185): keep **enforcement** of the eval evidence requirement advisory (PR review) for every prompt file except the `/spec` CI leg that already blocks; the contributor obligation to run the eval on a behavioral change stays MUST. Do not add a new blocking gate. Rationale:

- The hook-ROI reduction program (#3197) is removing gates and re-homing them into deterministic layers, not adding new blocking hooks.
- Two distinct automation options exist, and they are not the same deliverable. Option 1 is Deliverable A of #3185: deterministic evidence enforcement (check that eval evidence exists for a changed prompt file) in `scripts/validation/pre_pr.py` plus a CI leg. It needs no LLM and no cost model, reusing changed-path detection (the paths-filter mechanism the `/spec` leg uses to trigger) and then checking for committed eval evidence; it is deferred only on ROI grounds. Option 2 is separate and out of scope for Deliverable A: running the behavioral evals themselves in CI on every prompt change, which spawns LLM calls per change and stays deferred until the cost model is validated.
- This ADR's own Future path already defers broad CI eval automation "until the eval runner stabilizes and cost model is validated." One exception already shipped: the `/spec` leg runs the behavioral eval for `spec.md` because that command is high-traffic and its scenario set is maintained.
- The acceptance gate inside `eval-prompt-change.py` remains real and is used both by the `/spec` CI leg and by any contributor who runs an eval before a PR.

If a broader deterministic gate is later warranted (Deliverable A), it belongs in `scripts/validation/pre_pr.py` plus a CI leg with real change-to-evidence matching, not a PreToolUse hook. Running the behavioral evals for all prompt files in CI stays deferred until the cost model this ADR defers is validated.

## Reversibility Assessment

| Criterion | Assessment |
|-----------|------------|
| Rollback capability | Methodology can be dropped without affecting prompts or structural tests |
| Vendor lock-in | Uses Anthropic API (already a project dependency) |
| Exit strategy | Revert to manual testing or evolve to golden corpus |
| Legacy impact | None. Additive to ADR-023. |
| Data migration | Scenarios are plain Python files, portable |

**Reversal triggers**: If eval maintenance cost exceeds the value of regressions caught, or if model behavior becomes too nondeterministic for scenario-based assertions.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| ADR-023 structural tests | Complementary | Add cross-reference to this ADR | Low |
| PR template | Direct | Add eval score reporting fields | Low |
| CI workflows | Indirect | `spec.md` evals run as a blocking CI leg (`.github/workflows/slash-command-quality.yml`); other prompt files are not CI-enforced yet | Low |
| `.agents/testing/prompt-eval-methodology.md` | Source document | Add ADR-057 back-reference | Low |

## Related Decisions

- [ADR-023](ADR-023-quality-gate-prompt-testing.md): Structural validation for quality gate prompts. This ADR fills the behavioral gap ADR-023 explicitly deferred.
- [ADR-010](ADR-010-quality-gates-evaluator-optimizer.md): Quality gate patterns. Behavioral evals extend the quality gate concept to prompt correctness.

## References

- [Issue #1686](https://github.com/rjmurillo/ai-agents/issues/1686): Stop-condition fix that proved behavioral evals catch regressions structural tests miss
- [Issue #1688](https://github.com/rjmurillo/ai-agents/issues/1688): Source issue requesting this methodology formalization
- [`.agents/testing/prompt-eval-methodology.md`](/.agents/testing/prompt-eval-methodology.md): Detailed methodology document (source material for this ADR)
- [`.agents/security/benchmarks/test_agent_review_quality.py`](/.agents/security/benchmarks/test_agent_review_quality.py): Scenario-based test template
- [`.agents/steering/testing-approach.md`](/.agents/steering/testing-approach.md): Pester testing conventions with cross-reference to behavioral evals
