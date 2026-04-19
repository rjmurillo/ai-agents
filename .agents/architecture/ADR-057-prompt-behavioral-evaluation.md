---
status: proposed
date: 2026-04-19
decision-makers: ["architect", "user"]
consulted: ["qa", "security", "critic"]
informed: ["implementer", "analyst", "devops"]
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

A prompt change passes behavioral evaluation when all three criteria hold:

1. `after_score >= before_score` (no regression on existing scenarios)
2. Any scenario the change targets moves from fail to pass
3. No scenario flips from pass to fail without explicit justification in the PR. Intentional trade-offs are acceptable when the PR documents the rationale.

#### Security-Critical Prompt Tier

Prompts in the security domain (security agent, quality gate security prompts) require a stricter gate:

- Run each scenario a minimum of 5 times
- Require 100% pass rate across all runs (no flakiness tolerance)
- Scenario files must be reviewed by a CODEOWNERS-designated reviewer before merge

#### Flakiness Protocol

For non-security prompts, when a scenario produces inconsistent results across runs:

- Run the scenario 3 times minimum
- A scenario passes if it succeeds in at least 2 of 3 runs
- Document the flaky scenario in the PR with observed pass/fail ratio
- If flakiness rate exceeds 40% on any scenario, investigate before merging

### When to Run

| Trigger | Required? | Rationale |
|---------|-----------|-----------|
| Prompt change alters instructions, thresholds, or decision logic | Yes | Direct behavioral impact |
| Prompt change alters text structure only | No (structural tests suffice) | No behavioral risk |
| Ambiguous (rewording that may shift semantics) | Yes (tiebreaker: run evals) | When in doubt, treat as behavioral |
| Monthly for prompts under active iteration (modified in last 30 days or with open linked issues) | Recommended | Detect model drift |
| After Anthropic model version bump | Yes | Catch interpretation shifts |

### Scenario Adequacy

Minimum requirements for scenario coverage:

- At least one scenario per decision branch the prompt change introduces or modifies
- At least one regression scenario for existing behavior the change could affect
- Scenario coverage is reviewed as part of the PR review process
- A prompt with 0 scenarios does not satisfy the gate, even if no behavioral change is claimed

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

- Behavioral regressions in prompt changes are caught before merge
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

Compliance verified by:

1. PR description includes before/after eval scores when the change modifies prompt instructions or decision logic
2. Scenarios are committed to version control before the PR merges
3. No scenario flips from pass to fail without explicit justification in the PR description
4. Monthly eval runs are logged for prompts under active iteration (modified in last 30 days or with open linked issues)

### Enforcement Path

- **Immediate (this ADR)**: PR reviewers check for eval scores in PR descriptions. Code review is the enforcement mechanism.
- **Near-term**: Update PR template to include an eval score section with checkboxes for behavioral prompt changes.
- **Future (explicit non-goal for now)**: CI automation of eval runs. Deferred until eval runner stabilizes and cost model is validated.

API keys for eval runners MUST be loaded from environment variables. Hardcoded keys in scenario files or runner scripts are prohibited.

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
| CI workflows | Indirect | No change required (evals are pre-merge, not CI-enforced yet) | Low |
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
