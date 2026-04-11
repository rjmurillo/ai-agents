---
description: Prove it works. Multi-dimensional quality validation across functional, non-functional, security, DevOps, DX, and observability. Run after /build.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(gh:*), Bash(python3:*), Bash(pytest:*), Bash(npm test:*), Bash(uv:*), Bash(pester:*)
argument-hint: [component-or-failure-description]
---

@CLAUDE.md

Test: $ARGUMENTS

If $ARGUMENTS is empty, test the current branch diff against the base branch.

## Step 0: Classify PR Type

Detect the base branch from `gh pr view --json baseRefName` or fall back to `main`. Run `git diff origin/<base-branch> --name-only` and classify changed files:

| Type | Patterns | Gates to Run |
|------|----------|--------------|
| CODE | *.py, *.ps1, *.ts, *.js, *.cs | All 6 gates |
| WORKFLOW | *.yml in .github/workflows/ | Gates 1, 3, 4 |
| CONFIG | *.json, *.yaml (non-workflow) | Gates 3, 4 |
| DOCS | *.md, *.txt, *.rst | Gate 5 only |
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

Task(subagent_type="critic"): You are a developer advocate reviewing from the consumer perspective. Would a new contributor understand this code? Would the API frustrate or delight? Evaluate:

1. **API ergonomics** - Consumer perspective. Are signatures intuitive? Error messages helpful?
2. **Documentation** - Is changed behavior documented? Are code comments accurate (not stale)?
3. **Debuggability** - Can a developer diagnose failures from logs alone? Stack traces preserved?
4. **Onboarding** - Would a new contributor understand this code? Are conventions followed?
5. **Tooling** - Does this work with existing linters, formatters, IDE support?

Output: `VERDICT: PASS|WARN|CRITICAL_FAIL` with findings array.

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
- [SEVERITY] (file:line) description — recommendation
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
