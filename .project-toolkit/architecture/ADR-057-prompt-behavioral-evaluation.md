---
id: ADR-057
status: accepted
date: 2026-11-25
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

Adopt scenario-based LLM evaluation as the standard method for validating behavioral correctness of prompt changes. This methodology is documented in `.project-toolkit/testing/prompt-eval-methodology.md` and is now elevated to architectural policy.

### Scope: Files Requiring Behavioral Evaluation

| Category | Path Patterns |
|----------|---------------|
| Commands | `.claude/commands/*.md` |
| Quality gate prompts | `.github/prompts/*.md` |
| Security prompts | `.project-toolkit/security/prompts/*.md` |
| Agent definitions (Claude Code) | `.claude/agents/*.md` |
| Agent definitions (published) | `src/claude/*.md`, `src/copilot-cli/*.md`, `src/vs-code-agents/*.md` |
| Skill definitions | `.claude/skills/*/SKILL.md` |

Excluded from behavioral eval: `CLAUDE.md`, `README.md`, `INDEX.md`, `AGENTS.md`, and `.template.` files.

### Core Pattern

Each evaluation consists of:

1. **Scenarios**: Named input conditions with expected verdicts. A scenario may also carry a reason-contains substring, which is an informational signal and never gates
2. **Runner**: Invokes the LLM with prompt text plus scenario input, parses the verdict
3. **Before/after comparison**: Runs all scenarios against the prompt before and after the change, computes score delta

### Acceptance Gate

The acceptance gate returns FAIL on a regression. It does not mandate an improvement on every edit, and no CI check blocks a merge on its result (see Amendment 2026-10-02 and ADR-114). The one exception is an ADR-127 gated skill change, where the deterministic evidence check blocks a recomputed FAIL and any missing or invalid evidence (Amendment 2026-11-25). A prompt change passes behavioral evaluation when these criteria hold:

1. `after_score >= before_score` (no regression on existing scenarios). Both scores cover only scenarios with a stable base result; see criterion 4.
2. No scenario with a stable base result flips from pass to fail. A scenario passes on its verdict alone (the controlled label the grader is told to emit); the free-text reason never decides pass or fail. Every such pass-to-fail flip is recorded in `regressions` and blocks the gate automatically; the gate has no mechanism to accept a "justified" regression. The gate returns FAIL, but no CI check blocks a merge on that result, except for an ADR-127 gated skill change (Amendment 2026-11-25). The `/spec` eval in `.github/workflows/slash-command-quality.yml` runs only after a reviewer approves the `agent-claude` environment, and its check is non-blocking (see Amendment 2026-10-02). A deliberate behavior change still lands by updating the scenario expectations alongside the prompt in the same change, so the new expectations move with the intended behavior and the gate passes when it is run. An ADR-127 gated skill change is the exception: scenarios, including any dropped through `retired.json`, land in a commit before the first commit that touches the skill (its `templates/skills/<name>.SKILL.md.tmpl` or any file under `src/claude/skills/<name>/` or `.claude/skills/<name>/`, `scripts/` included) and then stay frozen, and a kept scenario's `expected_verdict` may not change (Amendment 2026-11-25). A reviewer who sees a FAIL, or no eval run at all, carries the judgment at PR review (see Amendment 2026-07-22).
3. Flakiness on any scenario stays at or below the 40% block threshold.
4. A stable baseline exists. A base scenario is unstable when it meets the pass threshold without passing every scored run (`is_base_unstable`: `passed` and `flaky`), or when it was scored on fewer runs than the tier requires (3 non-security, 5 security; the constants behind `insufficient_scored_before`). Stability is judged on scored runs, not requested runs. The base prompt never changes, so a swing is sampling noise, and a base scored once says nothing about stability. A base that fails the threshold (for example 1 of 3) is not unstable: it satisfies the baseline and cannot regress, which is intended. An unstable scenario is excluded from `regressions` and from both scores, and is reported in `base_unstable_scenarios` (in `base_unstable_security_scenarios` on the security tier) with `excluded_count`. The comparison is conclusive only when `scored_scenario_count >= max(1, ceil(total_scenarios / 2))` (`has_stable_baseline`). Below that floor the verdict is FAIL with an `inconclusive_reason` naming the stable and total counts. A comparison that omits `scored_scenario_count` derives the stable count from the gate's own exclusion set, and a supplied count can only lower it. A base that passes every scored run while the after side misses the pass threshold is still a regression.

The pass threshold is `ceil(2n/3)` of n scored runs, which is not monotone in the share of runs: required passes for n = 1 to 6 are 1, 2, 2, 3, 4, 4. The security tier is unchanged by this amendment: the after side must pass every scored run, and at least 5 runs must score.

Accepted limits of this criterion, stated so no reader assumes more: up to half the scenarios can be excluded and the gate still passes; a stable base (3 of 3) falling to 2 of 3 on the after side is not a regression, because the after side passes at 2 of 3; and a two-valued scenario such as D12 can be stable or pass by chance when the grader guesses, which removing the reason check no longer filters.

A right verdict with a reason lacking the expected substring is listed in `reason_mismatch_scenarios` (after side, passing runs only) for a reviewer to read. It does not fail the gate (Amendment 2026-09-30, Issue #5601).

A change that targets a failing scenario SHOULD move it from fail to pass. This is recorded as `has_improvement` and surfaced in the gate output, but it is not a hard pass requirement (see the 2026-06-01 relaxation note below).

#### Acceptance Gate Relaxation (2026-06-01, Issue #2197)

The gate has since gained two criteria, `no_insufficient_scored_runs` and `has_stable_baseline` (Amendment 2026-09-30). The original gate required `has_improvement` (at least one fail-to-pass flip, or `before_score == 1.0`) as a hard pass condition. This structurally blocked any legitimate change to a prompt whose base ref already had a failing scenario. Example: a documentation-consistency edit to `.claude/commands/spec.md` introduces no behavioral change and no regression, but pre-existing scenarios D13 and D14 fail on `main` (`before_score` 5/7 < 1.0). With zero fail-to-pass flips, `has_improvement` was false and the gate returned FAIL even though the change regressed nothing.

That outcome contradicts the gate's stated purpose: regression prevention (Decision Driver 2), not a mandate that every edit improve a score. The criterion "any scenario the change targets moves from fail to pass" was always conditional on the change targeting a scenario; it was never meant to apply to changes that target no scenario.

Relaxation: `has_improvement` is dropped as a hard pass requirement in `eval-prompt-change.py acceptance_gate()`. The gate now passes when `no_regression AND no_unexplained_regressions AND no_high_flakiness` hold (plus the security-critical 100%-pass requirement when applicable). `has_improvement` is still computed and reported in the gate criteria for visibility.

The FAIL verdict on a regression is preserved. Every pass-to-fail flip records the scenario in `regressions`, so `no_unexplained_regressions` fails and the gate returns FAIL when it runs. This holds even when an offsetting improvement keeps `after_score` flat (so `no_regression` stays true): the `regressions` list, not the score delta, is the authoritative verdict signal. The security-critical 100%-pass requirement is untouched: a security-critical run below 100% pass rate still returns FAIL regardless of improvement state. Returning FAIL does not block a merge; a reviewer acts on it (see Amendment 2026-10-02). An ADR-127 gated skill change is the exception (Amendment 2026-11-25).

#### Security-Critical Prompt Tier

Prompts in the security domain (security agent, quality gate security prompts) require a stricter gate:

- MUST: Run each scenario a minimum of 5 times. Enforced by `--security-critical` flag in eval-prompt-change.py.
- MUST: Require 100% pass rate across all runs. Enforced by acceptance gate in eval-prompt-change.py.
- SHOULD: Scenario files reviewed by a CODEOWNERS-designated reviewer before merge. Enforced by code review (not automated).

#### Flakiness Protocol

For non-security prompts, when a scenario produces inconsistent results across runs:

- MUST: Run the scenario 3 times minimum. Enforced by `DEFAULT_RUNS = 3` in eval-prompt-change.py.
- MUST: A scenario passes if it succeeds in at least 2 of 3 runs. Enforced by the ceiling threshold `-(-scored * 2 // 3)` (ceil(2/3 of scored runs)) in run_scenario_multi().
- MUST: If flakiness rate exceeds 40% on any scenario, the gate fails. Enforced by `FLAKINESS_BLOCK_THRESHOLD = 0.4` in acceptance_gate().
- SHOULD: Document the flaky scenario in the PR with observed pass/fail ratio. Enforced by code review.

### When to Run

| Trigger | Level | Enforced By | Rationale |
|---------|-------|-------------|-----------|
| Prompt change alters instructions, thresholds, or decision logic | MUST (obligation to run) | Enforcement advisory: run eval-prompt-change.py before PR; PR review verifies. No commit-time auto-block, and no blocking CI leg except for ADR-127 gated skill changes; the `/spec` CI leg runs only after environment approval and is non-blocking (see Amendments 2026-07-22, 2026-10-02, and 2026-11-25) | Direct behavioral impact |
| Prompt change alters text structure only | N/A | N/A (structural tests suffice) | No behavioral risk |
| Ambiguous (rewording that may shift semantics) | MUST (obligation to run) | Enforcement advisory: run eval-prompt-change.py before PR; PR review verifies. No commit-time auto-block, and no blocking CI leg except for ADR-127 gated skill changes; the `/spec` CI leg runs only after environment approval and is non-blocking (see Amendments 2026-07-22, 2026-10-02, and 2026-11-25) | When in doubt, treat as behavioral |
| Monthly for prompts under active iteration | SHOULD | Not automated (manual cadence) | Detect model drift |
| After Anthropic model version bump | SHOULD | Not automated (manual trigger) | Catch interpretation shifts |

### Scenario Adequacy

Minimum requirements for scenario coverage:

- MUST: A prompt with 0 scenarios does not satisfy the gate. Enforced by load_scenarios() which rejects empty scenario files.
- SHOULD: At least one scenario per decision branch the prompt change introduces or modifies. Enforced by code review.
- SHOULD: Enough scenarios that pass every base run to clear the stable floor. A scenario that passes only 2 of 3 base runs gives no regression protection (Amendment 2026-09-30). The gate is inconclusive (FAIL) unless at least `max(1, ceil(total_scenarios / 2))` scenarios have a stable base result.
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
| Security benchmarks | `.project-toolkit/security/benchmarks/` |
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

- Behavioral regressions are no longer caught automatically before merge. The `/spec` eval runs only when a human approves the `agent-claude` environment, and its check never blocks; for every in-scope prompt file outside ADR-127 gated changes the eval is advisory at PR review (see Amendments 2026-07-22, 2026-10-02, and 2026-11-25)
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

These gates run inside `eval-prompt-change.py`. They fire whenever the eval runner is invoked: advisorily when a contributor runs it before a PR, and as a non-blocking check when the `/spec` CI leg (`.github/workflows/slash-command-quality.yml`) invokes it, after environment approval, on a same-repo PR that changes the `/spec` command, its scenario set, or the eval runner. That leg always evaluates the `/spec` command behavior only; a change to the scenario set or the runner triggers a re-evaluation of that same command. No commit-time hook auto-invokes them (see Amendment 2026-07-22).

| Rule | Enforced By | Mechanism |
|------|-------------|-----------|
| Scenario file must contain >= 1 scenario | eval-prompt-change.py load_scenarios() | RuntimeError on empty file |
| after_score >= before_score (no regression) | eval-prompt-change.py acceptance_gate() | Gate returns FAIL |
| No stable-base scenario flips pass to fail | eval-prompt-change.py acceptance_gate() | Gate returns FAIL |
| Stable baseline (`has_stable_baseline`) | eval-prompt-change.py acceptance_gate() | Gate returns FAIL as inconclusive when `scored_scenario_count < max(1, ceil(total_scenarios / 2))`. A base scored on fewer than 3 runs (5 on the security tier) is unstable. Applies to the security tier too |
| Flakiness > 40% blocks gate | eval-prompt-change.py acceptance_gate() | FLAKINESS_BLOCK_THRESHOLD = 0.4 |
| Security prompts: 5 runs, 100% pass | eval-prompt-change.py --security-critical | Overrides runs, requires 100% pass_rate |
| Non-security: 3 runs, 2/3 pass | eval-prompt-change.py DEFAULT_RUNS | ceiling threshold `-(-scored * 2 // 3)` |
| --runs >= 1; non-security >= 3 | eval-prompt-change.py _parse_args() | parser.error on invalid value |
| API keys from environment variables | _anthropic_api.py load_api_key() | Reads env var, never hardcoded |

### Not enforced (code review only)

| Rule | Why Not Automated | Mitigation |
|------|-------------------|------------|
| Prompt/skill/agent changes require eval evidence | No commit-time hook (deleted in #3184); no CI leg blocks (the `/spec` leg is approval-gated and non-blocking), broader CI automation deferred (below). One exception: an ADR-127 gated skill change is blocked by `check_skill_rewrite_evidence.py` (Amendment 2026-11-25) | PR reviewer checks for eval evidence; advisory for every prompt outside ADR-127 gated changes, including the `/spec` CI leg |
| >= 1 scenario per decision branch | Requires understanding prompt semantics | PR reviewer checks scenario adequacy |
| >= 1 regression scenario | Same | PR reviewer checks |
| Monthly drift reruns | Scheduling concern, not commit-time | Manual cadence, future cron job |
| Model-bump reruns | No model version detection mechanism | Manual trigger after model updates |
| Cost ceiling ($50/month) | No cost aggregation across runs | Track manually, reassess if exceeded |
| Flaky scenario documentation in PR | Free-text in PR description | PR reviewer checks |

### Enforcement Path

- **Current**: No commit-time gate. The deleted PreToolUse hook that nominally blocked commits (`invoke_prompt_eval_gate.py`) was inert (it printed `{"decision":"deny"}` with exit 0, a payload the Claude Code harness ignores) and was removed in #3184. One CI leg runs the eval but does not block: `.github/workflows/slash-command-quality.yml` runs the `eval-prompt-change.py` acceptance gate against `.claude/skills/spec/SKILL.md` on same-repo PRs that change the `/spec` command, its scenario set (`tests/evals/spec-scenarios.json`), or the eval runner, only after a reviewer approves the `agent-claude` environment, and its workflow is listed in `advisory_agent_workflows` so its check never blocks a merge (Amendment 2026-10-02, ADR-114). That leg covers the `/spec` command only. For every other prompt, skill, and agent file the eval evidence requirement is advisory, verified at PR review, except an ADR-127 gated skill change, which `scripts/validation/check_skill_rewrite_evidence.py` blocks without committed evidence (Amendment 2026-11-25). The `eval-prompt-change.py` acceptance gate enforces regression, flakiness, and security-critical rules only when it is run.
- **Not automated**: Scenario adequacy, monthly cadence, cost tracking. These require human judgment or scheduling infrastructure not yet built.
- **Future**: Broader CI automation of eval runs, beyond the `/spec` leg that already ships. Deferred until the eval runner stabilizes and the cost model is validated.

## Amendment 2026-07-22 (Issue #3185): eval enforcement is advisory, not commit-blocking

The original ADR claimed a deleted Claude Code PreToolUse hook (`invoke_prompt_eval_gate.py`) blocked commits lacking eval evidence. That claim was false from the start: the hook emitted a `{"decision":"deny"}` payload with exit 0, which the harness ignores (the same bug class fixed in the historical `invoke_security_commit_gate.py`, Issue #2521). The hook never blocked a commit. Measured drain: from 2026-06-01, 108 commits touched eval-scoped prompt files while 1 commit added eval evidence.

#3184 deleted the inert hook. This amendment corrects the resulting torn references (the Acceptance Gate note, the "When to Run" and "Confirmation" tables, the Consequences list, the Enforcement Path, and the dependent-components table) so the ADR no longer points at a deleted file or asserts an automated block that never existed, and it scopes the one real block (the `/spec` CI leg) precisely.

Decision (Deliverable B of #3185): keep **enforcement** of the eval evidence requirement advisory (PR review) for every prompt file, including the `/spec` CI leg after Amendment 2026-10-02; the contributor obligation to run the eval on a behavioral change stays MUST. Do not add a new blocking gate. (Written when the `/spec` leg blocked; it no longer does, see Amendment 2026-10-02. Amendment 2026-11-25 adds one deterministic gate, scoped to ADR-127 gated changes.) Rationale:

- The hook-ROI reduction program (#3197) is removing gates and re-homing them into deterministic layers, not adding new blocking hooks.
- Two distinct automation options exist, and they are not the same deliverable. Option 1 is Deliverable A of #3185: deterministic evidence enforcement (check that eval evidence exists for a changed prompt file) in `scripts/validation/pre_pr.py` plus a CI leg. It needs no LLM and no cost model, reusing changed-path detection (the paths-filter mechanism the `/spec` leg uses to trigger) and then checking for committed eval evidence; it is deferred only on ROI grounds. Option 2 is separate and out of scope for Deliverable A: running the behavioral evals themselves in CI on every prompt change, which spawns LLM calls per change and stays deferred until the cost model is validated.
- This ADR's own Future path already defers broad CI eval automation "until the eval runner stabilizes and cost model is validated." One exception shipped: the `/spec` leg runs the behavioral eval because that command is high-traffic and its scenario set is maintained. After Amendment 2026-10-02 it runs only on approval and never blocks.
- The acceptance gate inside `eval-prompt-change.py` remains real and is used both by the `/spec` CI leg and by any contributor who runs an eval before a PR.

If a broader deterministic gate is later warranted (Deliverable A), it belongs in `scripts/validation/pre_pr.py` plus a CI leg with real change-to-evidence matching, not a PreToolUse hook. Running the behavioral evals for all prompt files in CI stays deferred until the cost model this ADR defers is validated.

## Amendment 2026-09-30 (Issue #5601): verdict-only scoring and a stable-base comparison

Two defects made the `/spec` gate block changes that altered no behavior. A scenario passed only when the grader echoed a phrase, so rewording moved the score. A scenario whose base result swung between runs produced regressions on its own, because the base prompt never changes.

Decision: the verdict alone gates a scenario, and `expected_reason_contains` is an informational signal. A base scenario that meets the 2-of-3 threshold without passing every run is excluded from `regressions` and the score comparison, and the gate fails closed when no base scenario is stable. The Acceptance Gate section above states the resulting criteria.

Follow-up decision (owner D3=A, after the full panel): the comparison needs a stable fraction. `has_stable_baseline` requires `scored_scenario_count >= max(1, ceil(total_scenarios / 2))`, and below it the verdict is FAIL as inconclusive. A base scored on fewer runs than the tier requires (3 non-security, 5 security) counts as unstable, so a single scored run cannot form the baseline. The security tier is unchanged: the after side must pass 5 of 5 scored runs. A failing base satisfies the baseline and cannot regress, which is intended.

Trade-offs, accepted. Verdict-only scoring trades false blocks for false passes: a right-answer-wrong-reason pass is no longer caught, and a real regression on a scenario that passes only some base runs is reported, not blocked. The ceiling threshold is non-monotone: required passes for n = 1 to 6 scored runs are 1, 2, 2, 3, 4, 4.

Accepted limits with revisit triggers. The stable set is drawn from one noisy 3-run base sample, so a 3/3 draw on a noisy base is treated as stable. Revisit after 10 live gate runs, when the base-unstable exclusion rate exceeds 25%, or when a scenario flips between stable and unstable across reruns. The long-term design is a pooled paired test. Two further limits share that trigger: a stricter after-side threshold for scenarios that were stable at base, and a chance correction for two-valued scenarios (critic findings 8 to 10 in the debate log). The provider-outage limit recorded here as exit 0 is superseded by the 2026-10-13 amendment. A base that passes every scored run and an after side that fails still blocks. A structured grader field that keeps a right-answer-wrong-reason check remains an option, but it needs live grader runs to author.

## Amendment 2026-10-02: the /spec CI leg is non-blocking and approval-gated

ADR-114 sets the policy: agent workflows run only after approval of their provider environment and never block a merge. The `/spec` leg reads `ANTHROPIC_API_KEY`, so it runs in `agent-claude`. For this ADR that means the `/spec` CI leg (`.github/workflows/slash-command-quality.yml`, job `validate-slash-commands`) is non-blocking and approval-gated. Prompt regressions are no longer caught automatically before merge. A reviewer dispatches or approves the eval for prompt-file diffs and reads the result. The acceptance gate itself is unchanged and still returns FAIL on a regression when it runs.

## Amendment 2026-10-13 (Issue #6148): a provider outage exits 3

The 2026-09-30 amendment accepted a fail-open provider outage: the script exited 0 without running. Issue #6148 closes security finding 19, which required a fix before the eval becomes a required check.

Decision: a provider outage exits 3 (ADR-035 external failure) and prints `ERROR: provider unavailable`, so the gate never reports success without running. `_is_provider_outage` classifies an error as an outage when its lowercased message contains any one of these 11 literal substrings: `usage limit`, `rate limit`, `too many requests`, `timed out`, `network error`, `returned http 408`, `returned http 429`, `returned http 500`, `returned http 502`, `returned http 503`, `returned http 504`. Each status marker is the full spaced token, not `returned http` plus a status code elsewhere in the message.

A billing error (`error=billing`) is checked first and exits 4. Any other execution fault exits 3 with `ERROR: eval failed`. The caller decides whether to tolerate exit 3. The `/spec` CI leg stays advisory under ADR-114, so a red outage leg does not block a merge.

## Amendment 2026-11-25 (ADR-127 decision 9): a deterministic check blocks gated skill changes

ADR-127 decision 7 makes this runner the acceptance gate for a skill rewrite, which it calls a gated change.
Decision 9 requires a check that enforces that gate in code. The 2026-07-22 amendment said "Do not add a new blocking gate."
It also named `pre_pr.py` plus a CI leg as the path for a later deterministic gate (Deliverable A of #3185).
This amendment takes that path, for gated changes only.

Decision:

1. `scripts/validation/check_skill_rewrite_evidence.py` blocks a gated change that lacks valid evidence.
   `pre_pr.py` runs it as the `Skill Rewrite Evidence (ADR-127)` gate.
   `pr-validation.yml` runs it as the `Check ADR-127 skill rewrite evidence` step of `Validate PR`.
   It is deterministic and calls no model. ADR-114 is unchanged: no agent verdict blocks a merge.
2. Every other prompt file stays advisory. That includes a prose edit to an untagged or `reference` skill.
   The MUST to run the eval stays with the author, read at review.
3. The runner's `--output` gains an `identity` block. It records the prompt path and the sha256 of the exact after-side text the model read.
   That text is the rendered `SKILL.md` plus every `references/*.md` beside it.
   It also records the scenario path and sha256, the `--base-ref` name, the commit it resolved to, and the model.
   A value the runner cannot resolve is written as `null`. The check fails closed on it.
   Pass `--prompt` as the repository-relative rendered path, such as `src/claude/skills/ship/SKILL.md`. Any other form fails the path match.
   This adds output fields only. The text sent to the model does not change.
4. The check reads the diff from the merge base to the commit under test.
   CI passes the PR head commit, so CI hashes the tree the author ran the eval on, not the synthetic merge commit.
   A skill is gated when any of these holds:
   its `metadata.shape` changes, except adding `reference` where none existed;
   it is a `driver` on either side and its prompt surface changed;
   the branch touches `evals/skill-rewrites/<name>/`, which is how an author declares a gap-audit row;
   or at least 3 lines of 32 or more characters leave `SKILL.md` and reappear in `references/`.
   Precision is inferred from 5 hits, and recall is unknown. A reworded or split move slips past it.
5. A new skill has no base to hold against, and a deleted skill has nothing to run, so neither is gated.
   A new skill that lands beside a deleted one may be a rename, so it is gated. Its eval uses the runner's `--renamed-from`.
   This reads ADR-127 decision 7, trigger 1, as not covering a brand-new driver. Read literally, that trigger would block every new driver forever: the carried floor needs base runs that cannot exist.
   The ADR-127 owner confirmed this reading on 2026-11-25, and ADR-127 decision 7 now states it. A new driver still owes the decision 8 tests.
6. For a gated skill the check requires `tests/evals/<name>-scenarios.json` and a results file under `evals/skill-rewrites/<name>/`.
   Candidates are the results files that record the head prompt-surface sha256.
   The one committed first sets the verdict. A matching file already on the base ref counts as first, since that surface was evaluated before.
   It must match the other three identities too.
   Its base commit must be an ancestor of the base ref.
   The check recomputes each run's pass from its verdict label and the scenario file. It never reads `gate.verdict` as truth.
   It then calls the runner's own `acceptance_gate`. A file whose recorded verdict disagrees with its runs fails.
7. It enforces the ADR-127 decision 7 floors the runner does not compute.
   The file needs at least 8 scenarios, and at least 6 must pass every scored base run.
   A scenario that fails or is unstable on base must pass every scored after run.
8. It enforces the scenario rules of decision 7 items 8 and 10.
   The scenario file may not change in or after the first commit that touches the skill. A merge's own edits count.
   A kept scenario may not change its `expected_verdict` since the merge base.
   A scenario dropped since the merge base needs a row in `retired.json` naming a test that exists at head.
9. Results files are append-only on the branch (decision 7 item 9). An edit, a delete, or a second add of the same path fails.
10. A gated branch may not also change the runner (`scripts/eval/eval-prompt-change.py` or `scripts/eval/_*`), the check's three modules, its `pre_pr` registration, or `pr-validation.yml`.

Rollback: a false block is fixed by one PR that removes the CI step and the `pre_pr` registration.
The check has no skip flag, so a revert is the only way past it.

Security seat recommendation (ADR-127 review): adopted, as an allowlist. This rule goes past decision 9.
A skill the branch touches that is tagged `reference` may hold only these tools: Read, Grep, Glob, LS, Skill, TodoWrite, WebFetch, WebSearch, AskUserQuestion, and the working-tree write tools.
Delegation tools (Task, Agent) fail, since a subagent can hold any grant.
It may also hold a read-only MCP tool, a read-only Bash command such as `git diff`, or a Bash grant that runs its own `scripts/`.
A Bash grant fails when it holds `..`, a shell operator, or a git flag that writes or runs a program (`--output`, `--ext-diff`, `-O`).
`git grep` is not on the list. A write tool beside any Bash grant fails. The model could write a script, or a git config that sets `diff.external`, and run it.
Any other grant fails. A list-form `allowed-tools` is read the same way as a string.
A wider grant lets the model act as a driver, so the tag would dodge the driver trigger.
A reference skill whose own script pushes is still a driver. A reviewer owns that case.
At `c0b72f8539` (2026-11-25) no template sets `metadata.shape`, so the rule blocks no current file.

Limits, which stay with the reviewer:

- The check cannot prove a model ran. A hand-built results file with matching hashes passes.
- The branch history is the author's. A rebase can drop a failed run or reorder the scenario commit before the check reads it.
- A PR that edits the check or the runner changes what the check does. Item 10 stops honest drift only. CODEOWNERS covers `scripts/validation/` but not `scripts/eval/`.
- The results file states `security_critical`. Nothing records which skills are security-critical.
- The base commit is only proved to be an ancestor of the base ref, not the exact fork point.
- A `pull_request` run uses the PR's own copy of `pr-validation.yml`, so a PR can edit the step out. CODEOWNERS covers `.github/workflows/`.
- The check reads the PR head. If `main` edits the same skill, the merged tree is never evaluated.
- In CI the runner module loads from the merge-commit tree while blobs are read at the PR head. A `main` change to the runner's hashing would show as an identity mismatch.
- In the merge queue, the check reads the queued tree. A second queued PR that edits the same skill fails, because no results file records the combined surface.
- The checkout leaves its token in `.git/config` for the whole job. Earlier steps in the job run PR code the same way.
- The grant rule reads the grant text. A `*` in a grant lets the model add flags when it runs, so `Bash(git diff:*)` can still take `--output`.
- The own-script grant accepts any path prefix before `skills/<name>/scripts/`, so it does not prove the path is inside the plugin root.
- A read-only MCP tool is judged by its name. A write tool with a read verb in its name and no write word passes.
- A symlinked reference file hashes as its link text in the check, while the runner reads the target. The two then disagree and the check fails closed.

What stays manual, because no mechanical test was found:

- An untagged skill that ADR-127 decision 1 says must be a driver.
- A step moved into a script. Prose and code share no lines to match.
- A section moved and reworded in the same change.
- A gap-audit row the author does not declare.
- The three-first-runs cap, and the base-run output the scenario commit must carry (decision 7 items 8 and 9).

Measurement behind item 4: an earlier draft gated any added `scripts/` or `references/` file plus a removed `SKILL.md` line.
Over the 400 first-parent commits of `main` to `c0b72f8539` (2026-11-25), it fired on 51 skill changes, mostly feature adds.
The verbatim-line rule fired on 5 skill changes in 4 commits over the same range at `c0b72f8539` (2026-11-25).
In each, `SKILL.md` shrank and a reference file gained the removed lines. No labeled set of missed moves exists, so the miss rate is unknown.

Debate log: `.project-toolkit/critique/ADR-057-debate-log-2.md`.

## Reversibility Assessment

| Criterion | Assessment |
|-----------|------------|
| Rollback capability | Methodology can be dropped without affecting prompts or structural tests. The ADR-127 evidence gate (Amendment 2026-11-25) reverts with one PR that removes its CI step and `pre_pr` registration; it has no skip flag |
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
| CI workflows | Indirect | `/spec` evals run as an approval-gated, non-blocking CI leg (`.github/workflows/slash-command-quality.yml`). `Validate PR` (`.github/workflows/pr-validation.yml`) runs the deterministic ADR-127 evidence check, which blocks gated skill changes only. Other prompt files are not CI-enforced | Low |
| `scripts/eval/eval-prompt-change.py` | Direct | `--output` carries an `identity` block (Amendment 2026-11-25) | Low |
| `.project-toolkit/testing/prompt-eval-methodology.md` | Source document | Add ADR-057 back-reference | Low |

## Related Decisions

- [ADR-023](ADR-023-quality-gate-prompt-testing.md): Structural validation for quality gate prompts. This ADR fills the behavioral gap ADR-023 explicitly deferred.
- [ADR-010](ADR-010-quality-gates-evaluator-optimizer.md): Quality gate patterns. Behavioral evals extend the quality gate concept to prompt correctness.
- [ADR-127](ADR-127-workflow-skills-are-script-drivers.md): Decision 7 makes this runner the gate for skill rewrites. Decision 9 requires the evidence check that Amendment 2026-11-25 records.

## References

- [Issue #1686](https://github.com/rjmurillo/ai-agents/issues/1686): Stop-condition fix that proved behavioral evals catch regressions structural tests miss
- [Issue #1688](https://github.com/rjmurillo/ai-agents/issues/1688): Source issue requesting this methodology formalization
- [`.project-toolkit/testing/prompt-eval-methodology.md`](/.project-toolkit/testing/prompt-eval-methodology.md): Detailed methodology document (source material for this ADR)
- [`.project-toolkit/security/benchmarks/test_agent_review_quality.py`](/.project-toolkit/security/benchmarks/test_agent_review_quality.py): Scenario-based test template
- [`.agents/steering/testing-approach.md`](/.agents/steering/testing-approach.md): Pester testing conventions with cross-reference to behavioral evals
