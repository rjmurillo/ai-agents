---
name: test
version: 1.0.0
description: Prove a change works across six gates covering functional, non-functional, security, DevOps, developer experience, and observability quality. Use when you say `prove this works`, `run the test gates`, or `validate this change`, and run it after build. Do NOT use to write the implementation or its first tests (use build), and do NOT use to run pre-flight and open a PR (use ship).
license: MIT
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
argument-hint: component-or-failure-description
user-invocable: true
---

# Test

Six quality gates, each dispatching its own agent, skipped by PR type so no
agent burns on a dimension the diff cannot touch.

Migrated from `.claude/commands/test.md` under ADR-064, which makes skills the
single user-invocable surface.

@CLAUDE.md

## Triggers

`prove this works`, `run the test gates`, `validate this change`,
`is this ready for review`

## Arguments

Test: $ARGUMENTS

If `$ARGUMENTS` is empty, test the current branch diff against the base branch.

## Cross-Harness Hook Routing

If the diff touches Claude Code or GitHub Copilot CLI hooks, dispatchers,
generated shims, event translation, or hook output:

1. Invoke `Skill(skill="agent-harness-reference")` to load the pinned contract.
2. Run the verification path in
   `Skill(skill="ai-agents-portability-campaign")`.
3. Require unit coverage for translation plus a real-harness smoke test for
   each affected harness.
4. Treat documentation silence as an unknown to probe, not permission to guess.

## Step 0: Classify PR Type

Detect the base branch from `gh pr view --json baseRefName` or fall back to `main`. Run `git diff origin/<base-branch> --name-only` and classify changed files:

| Type | Patterns | Gates to Run |
|------|----------|--------------|
| CODE | `*.py`, `*.ps1`, `*.ts`, `*.js`, `*.cs` | All 6 gates |
| WORKFLOW | `*.yml` in `.github/workflows/` | Gates 1, 3, 4 |
| CONFIG | `*.json`, `*.yaml` (non-workflow) | Gates 3, 4 |
| DOCS | `*.md`, `*.txt`, `*.rst` | Gate 5 only |
| MIXED | Combination | Apply per-file rules |

Print: `PR TYPE: [type]. Running gates: [list].`

Skip non-applicable gates. Do not waste agent invocations on irrelevant dimensions.

## Gate 1: Functional Testing

Invoke Skill(skill="code-qualities-assessment") for quality baseline.

Task(subagent_type="qa"): You are a senior QA engineer. Your job is to catch issues that will cause production incidents. Be skeptical. Cite specific file:line evidence for every finding. Evaluate:

1. **Unit coverage** - Each method in isolation, dependencies injected. Every new function has at least 1 test.
2. **Integration coverage** - Contracts between components verified. Cross-module boundaries exercised.
3. **Acceptance coverage** - Each requirement has a passing test. Map to acceptance criteria from /spec output.
4. **Edge cases** - Null/empty/boundary values, invalid types, concurrent access where applicable.
5. **Error paths** - Every catch/error branch tested. No silent swallowing. Resources cleaned up on failure.
6. **Regression risk** - High-risk areas (auth, data persistence, payments) require full coverage regardless of change size.

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL` with findings array.

## Gate 2: Non-Functional Testing

Task(subagent_type="analyst"): You are a performance and reliability engineer. Focus on failure modes, not the happy path. Use measurable criteria, not subjective judgments. Evaluate:

1. **Performance** - No N+1 queries, no O(n*m) in hot paths, no blocking calls in async context.
2. **Scalability** - Will this bottleneck under load? Connection pooling, caching strategy, pagination.
3. **Reliability** - Retry logic, circuit breakers, graceful degradation. Failure modes tested.
4. **Complexity** - Cyclomatic complexity <=10. Methods <=60 lines. No deep nesting.
5. **Maintainability** - Readability, naming clarity, consistency with existing patterns.

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL` with findings array.

## Gate 3: Security Testing

Invoke Skill(skill="security-scan") for CWE pattern detection.

Task(subagent_type="security"): You are a security auditor performing OWASP Top 10 review. Assume every input is malicious. Reference CWE numbers for every finding. Evaluate:

1. **Injection** - Shell (CWE-78), XSS (CWE-79), SQL (CWE-89). No string interpolation in queries.
2. **Authentication** - Session handling, credential storage, token validation.
3. **Secrets** - No hardcoded API keys, passwords, tokens in diff. Secrets via environment only.
4. **Input validation** - All user-facing inputs validated. LLM output treated as untrusted.
5. **Dependencies** - New packages reviewed for known vulnerabilities. Versions pinned.

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL` with findings array including CWE references.

## Gate 4: DevOps Testing

Task(subagent_type="devops"): You are a build and release engineer. Focus on pipeline safety, reproducibility, and supply chain security. Evaluate:

1. **Pipeline impact** - Do changes affect CI/CD? Are workflow files valid YAML?
2. **Actions security** - Pinned to SHA? Permissions scoped minimally? No secrets in logs?
3. **Shell quality** - Input sanitization, exit code handling, error propagation.
4. **Build reproducibility** - Deterministic builds, locked dependencies, no floating versions.
5. **Artifact integrity** - Correct upload/download, retention policy, no sensitive data in artifacts.

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL` with findings array.

## Gate 5: Developer Experience (DX)

Invoke Skill(skill="orphan-ref-validator"). Reject the gate on `VERDICT: CRITICAL_FAIL` or `VERDICT: ERROR`; `VERDICT: WARN` is non-blocking and surfaces in the test summary. This mirrors the `build` skill's Mandatory Exit Gate 4 so a reference to a deleted skill or a missing script path is caught at `/test` as well as at `/build`. To diagnose a failure, re-run the skill with `--output human`; each finding shows `path:line` plus a one-line recommendation. Manifest count claims are not validated by anything: the marketplace count validator was retired in #2187 and orphan-ref-validator never took the work over. Its scanner emits only skill_name, script_path, and scan_truncated findings. The skill invocation is platform-agnostic; each platform mirror runs its own copy of `scan.py`. If pre-existing drift outside the PR's scope blocks the gate, fix it in the same PR (the directives at `<!-- orphan-ref-ignore -->` and `<!-- orphan-ref-ignore-file -->` are documented in the skill's SKILL.md).

Task(subagent_type="critic"): You are a developer advocate reviewing from the consumer perspective. Would a new contributor understand this code? Would the API frustrate or delight? Evaluate:

1. **API ergonomics** - Consumer perspective. Are signatures intuitive? Error messages helpful?
2. **Documentation** - Is changed behavior documented? Are code comments accurate (not stale)?
3. **Debuggability** - Can a developer diagnose failures from logs alone? Stack traces preserved?
4. **Onboarding** - Would a new contributor understand this code? Are conventions followed?
5. **Tooling** - Does this work with existing linters, formatters, IDE support?

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR` with findings array.

## Gate 6: Observability and Monitoring

Task(subagent_type="architect"): You are an SRE reviewing production readiness. If this code fails at 3am, can oncall diagnose it without reading the source? Evaluate:

1. **Logging** - Are meaningful events logged? Structured logging with correlation IDs?
2. **Metrics** - Are SLIs defined for new features? Latency, error rate, throughput tracked?
3. **Alerting** - Would failures trigger alerts? Are thresholds appropriate?
4. **Tracing** - Are distributed traces propagated? Span context preserved across boundaries?
5. **Health checks** - New services have liveness/readiness probes? Degradation detectable?

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL` with findings array.

## Principles

- **Testability is design feedback**: Hard to test means poor encapsulation, tight coupling, Law of Demeter violation, weak cohesion, or procedural code.
- **Tests are proof**: A passing test is evidence. A missing test is a gap in knowledge.
- **Hypothesis-driven debugging**: When a test fails, form a hypothesis before changing code. Verify the hypothesis. Then fix.
- **Defense in depth**: Assume the happy path works. Focus on failure modes.

## Process

1. Identify what changed (git diff against base branch)
2. Classify PR type (Step 0). Skip non-applicable gates.
3. Run applicable gates sequentially. Each gate dispatches its own agent.
4. If any gate produces CRITICAL_FAIL: continue remaining gates (findings are additive). Mark overall verdict as CRITICAL_FAIL immediately.
5. For test failures: hypothesis, verify, fix (never change code without understanding why)
6. Invoke Skill(skill="quality-grades") to synthesize gate verdicts into overall quality score.

## Output

Each gate MUST produce a verdict line and findings array:

```text
GATE: [name]
VERDICT: PASS|WARN|CRITICAL_FAIL
FINDINGS:
- [SEVERITY] (file:line) description: recommendation
```

Synthesize into overall report:

| Gate | Verdict | Findings | Evidence |
|------|---------|----------|----------|
| Functional | PASS/WARN/CRITICAL_FAIL | Count | file:line citations |
| Non-Functional | PASS/WARN/CRITICAL_FAIL | Count | file:line citations |
| Security | PASS/WARN/CRITICAL_FAIL | Count | CWE references |
| DevOps | PASS/WARN/CRITICAL_FAIL | Count | file:line citations |
| DX | PASS/WARN/CRITICAL_FAIL | Count | file:line citations |
| Observability | PASS/WARN/CRITICAL_FAIL | Count | file:line citations |

**Overall verdict**: CRITICAL_FAIL if any gate fails. WARN if any gate warns. PASS if all gates pass.

## Verification

- [ ] PR type classified before any gate ran, and the skipped gates named
- [ ] Every applicable gate produced a `VERDICT:` line and a findings array
- [ ] Every finding cites `file:line`, and every security finding cites a CWE
- [ ] A CRITICAL_FAIL in one gate did not stop the remaining gates
- [ ] Each test failure was diagnosed by hypothesis before any code changed
- [ ] Gate verdicts synthesized into one overall verdict via quality-grades

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Stopping at the first CRITICAL_FAIL | Findings are additive, so an early stop hides the rest and buys a second round | Mark the overall verdict and keep running the gates |
| Running all six gates on a docs-only diff | Burns five agent invocations on dimensions the diff cannot affect | Classify in Step 0 and skip |
| A finding with no `file:line` | The reader cannot act on it, and it cannot be verified or refuted | Cite the location, and a CWE for security findings |
| Changing code to make a red test pass | Fixes the symptom and often moves the defect | Form a hypothesis, verify it, then fix |
| Treating a passing suite as proof of coverage | A green run says the tests that exist pass, not that the risky paths have any | Check error paths and edge cases per Gate 1 |

## Extension Points

- **A seventh gate.** Add a `## Gate 7` section, a row in the Step 0 type table,
  and a row in the output table together, so a gate cannot run unreported.
- **New PR type.** Step 0's table maps patterns to gates; a new file class is a
  new row, not new prose.
- **Different synthesis.** Process step 6 delegates to `quality-grades`. A
  project scoring differently swaps that one call.
