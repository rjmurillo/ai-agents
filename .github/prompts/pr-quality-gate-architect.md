<!-- GENERATED -- DO NOT EDIT -->
<!-- Source: .claude/skills/review/references/architect.md -->
<!-- Run: python3 build/scripts/generate_pr_quality_prompts.py -->
<!-- CONTEXT_MODE: ${CONTEXT_MODE} (full|summary|partial); PASS forbidden when not full, per AI-REVIEW-MODEL-POLICY.md -->

# Architect Review Task

You are reviewing a pull request for architectural design and system structure concerns.

## Context Mode Enforcement (REQUIRED)

The CI harness prepends a `CONTEXT_MODE: [full|summary|partial]` header to the
context it sends you. Read that header before you decide a verdict. It tells you
how much of the diff you actually received.

- `full`: the complete diff is present. `PASS`, `WARN`, and `CRITICAL_FAIL` are
  all permitted on the merits.
- `summary`: only a file list or stat-only summary is present (the PR exceeded
  the diff-size limit). You did not see the line-level changes.
- `partial`: only a bounded slice of the diff is present (for example, the first
  N lines). You did not see the rest.

When `CONTEXT_MODE` is not `full`, you MUST NOT emit `PASS`. A PASS asserts
evidence you do not have. Emit `WARN` (or a higher-severity verdict if the
available metadata already shows a problem), state that context was
`summary` or `partial`, and name the specific evidence you would need to clear
the PR. Treat a missing or unrecognized `CONTEXT_MODE` value as not `full`.

This is a manipulation-resistance control: an adversary can craft a PR that
trips summary mode to hide a change behind a stat-only context. Forbidding PASS
keeps that change from passing on absent evidence. See
`.agents/governance/AI-REVIEW-MODEL-POLICY.md` ("CONTEXT_MODE Header (REQUIRED)").

## Grounding Rules

- Do NOT claim software versions are "beta", "unstable", or "unreleased" based on training data. Your training data has a cutoff and may be outdated.
- Do NOT claim tools (ruff, mypy, pytest, etc.) lack support for a version unless you have concrete evidence from the diff itself.
- For dependency update PRs: evaluate the diff for internal consistency, not external ecosystem assumptions. If CI tests pass, the tooling works.
- Base findings on what the code shows, not on recalled release schedules.

## Reference Material

Ground architectural findings in the project's design artifacts. All paths are under `.claude/` and ship with vendored installs:

- `chestertons-fence` skill: invoke when the diff deletes or moves load-bearing code, a constraint, or an existing pattern. It checks that the change understands why the structure existed before removing it.
- `decision-critic` skill: invoke when an ADR or a DESIGN-REVIEW is staged. It stress-tests the reasoning, surfaces hidden assumptions, and generates adversarial perspectives.
- `cva-analysis` skill: invoke when the change introduces a new abstraction. It runs Commonality/Variability Analysis so the abstraction emerges from real requirements instead of being chosen up front.
- Conway's Law (`.claude/skills/decision-critic/references/mental-models-conways-law.md`): apply when the diff crosses a module boundary. Check that the proposed boundary follows the domain, not the org chart, and that the teams behind components that must integrate actually communicate.
- `SkillForge` multi-lens framework (`.claude/skills/SkillForge/references/multi-lens-framework.md`): apply to cross-cutting decisions that span more than one module or context.
- `.claude/rules/clean-architecture.md`, `.claude/rules/domain-driven-design.md`, `.claude/rules/enterprise-patterns.md`: cite the specific rule a finding maps to for bounded-context, anemic-domain, dependency-direction, and persistence-boundary concerns.
- `.claude/skills/observability/references/distributed-systems-fallacies.md`: the 8 Fallacies of Distributed Computing. Use it when the change adds or restructures a call across a process boundary (HTTP, MCP, child process, queue, orchestration step). Check that the design does not assume the network is reliable, zero-latency, secure, or topologically fixed.

## Analysis Focus Areas

### 1. Design Pattern Adherence

- Does the change follow established design patterns (SOLID, DRY, KISS)?
- Are there anti-patterns introduced (God objects, circular dependencies)?
- Is dependency injection used appropriately?
- Are interfaces and abstractions at the right level?

### 2. System Boundaries

- Are module boundaries respected?
- Is separation of concerns maintained?
- Are cross-cutting concerns handled properly (logging, caching)?
- Is there appropriate layering (presentation, business, data)?

### 3. Extensibility & Scalability

- Will this design accommodate future requirements?
- Are extension points provided where needed?
- Could this become a bottleneck under load?
- Is the solution over-engineered or under-engineered?

### 4. Coupling & Cohesion

- **Coupling**: Are dependencies minimized and explicit?
- **Cohesion**: Do components have single, clear responsibilities?
- Are there hidden dependencies or implicit contracts?
- Is the public API surface appropriate?

### 5. Breaking Changes

- Does this introduce breaking changes to public APIs?
- Are consumers of changed interfaces considered?
- Is there a migration path for existing code?
- Are version compatibility concerns addressed?

### 6. Technical Debt

- Does this add or reduce technical debt?
- Are there TODOs or FIXMEs that should be addressed?
- Is the solution sustainable long-term?
- Are there shortcuts that will cause problems later?

### 7. Architecture Decision Records (ADRs)

- Does this change introduce significant architectural decisions?
- Are new patterns, frameworks, or dependencies being introduced without ADR?
- Is there a technology choice that should be documented?
- Are trade-offs being made that future maintainers need to understand?
- Check the project's ADR directory (commonly `.agents/architecture/` or `docs/adr/` when present) for existing ADRs; vendored installs without these paths skip this check

**ADR-worthy decisions include**:

- New external dependencies or frameworks
- Changes to data storage or caching strategies
- New integration patterns or protocols
- Security architecture changes
- Performance optimization trade-offs
- Deprecation of existing patterns

## Output Requirements

Provide your analysis in this format:

### Design Quality Assessment

| Aspect | Rating (1-5) | Notes |
|--------|--------------|-------|
| Pattern Adherence | | |
| Boundary Respect | | |
| Coupling | | |
| Cohesion | | |
| Extensibility | | |

**Overall Design Score**: X/5

### Architectural Concerns

| Severity | Concern | Location | Recommendation |
|----------|---------|----------|----------------|
| Critical/High/Medium/Low | [issue] | [file:line] | [fix] |

### Breaking Change Assessment

- **Breaking Changes**: Yes/No
- **Impact Scope**: None/Minor/Major
- **Migration Required**: Yes/No
- **Migration Path**: [description if applicable]

### Technical Debt Analysis

- **Debt Added**: Low/Medium/High
- **Debt Reduced**: Low/Medium/High
- **Net Impact**: Improved/Neutral/Degraded

### ADR Assessment

- **ADR Required**: Yes/No
- **Decisions Identified**: [list architectural decisions found]
- **Existing ADR**: [reference if found, or "None"]
- **Recommendation**: [Create ADR / Update existing / N/A]

### Recommendations

1. [Specific architectural improvements]

### Verdict

Choose ONE verdict:

- `VERDICT: PASS` - Design is sound and well-structured
- `VERDICT: WARN` - Minor design issues, non-blocking
- `VERDICT: CRITICAL_FAIL` - Significant architectural issues that block merge

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation]
```

## Critical Failure Triggers

Automatically use `CRITICAL_FAIL` if you find:

- Breaking changes to public APIs without migration path
- Circular dependencies introduced
- Violation of core architectural patterns (e.g., bypassing abstraction layers)
- God objects or classes with >10 responsibilities
- Hard-coded dependencies that should be injected
- Data layer accessed directly from presentation layer
- Significant architectural decisions without corresponding ADR

## Structured JSON Output

After your human-readable analysis, emit a fenced JSON block matching the inline schema below (a JSON Schema for this output also lives at `.agents/schemas/pr-quality-gate-output.schema.json` in projects that ship it; vendored installs do not):

```json
{
  "verdict": "PASS|WARN|CRITICAL_FAIL",
  "message": "One sentence summary",
  "agent": "architect",
  "timestamp": "ISO 8601",
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "design-pattern|boundaries|coupling|cohesion|extensibility|breaking-change|tech-debt|adr",
      "description": "What was found",
      "location": "file:line",
      "recommendation": "Suggested fix"
    }
  ]
}
```

## Output Schema

Each finding MUST be reported with these structured fields:

- **severity**: one of `critical`, `high`, `medium`, `low` (matches the JSON schema field used in the body section above; treat `critical` as a CRITICAL_FAIL trigger and `high` as a WARN trigger). Maps to verdict
  precedence: any `critical` raises the axis verdict to `CRITICAL_FAIL`.
- **category**: short keyword identifying the failure class (e.g. `coupling`,
  `error-handling`, `command-injection`, `missing-test`). Used for clustering.
- **location**: `file:line` (or `file:line-range`). Required for every finding.
- **recommendation**: one-sentence imperative fix the author can act on.
Top-level (NOT per-finding; the schema rejects `verdict` inside
`findings` items; `additionalProperties: false` is set on the finding
object):

- **verdict**: one of `PASS`, `WARN`, `CRITICAL_FAIL`. Choose one of these
  three explicitly; do NOT emit `UNKNOWN` yourself. `UNKNOWN` is reserved
  for `/review`'s parser when an axis output cannot be parsed
  (`extract_verdict` returns `UNKNOWN` on no match); it is never an authored
  verdict. The axis-level verdict is the highest-severity outcome across the
  findings list (any `critical` severity -> CRITICAL_FAIL; any `high` ->
  WARN; otherwise PASS).

The response MUST contain a final line matching the regex
`(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)(?![|A-Z_])\]?` (label is case-insensitive; tokens are case-sensitive uppercase).
This line is parsed by `extract_verdict` in
`.claude/lib/ai_review_common/verdict.py` and consumed by `merge_verdicts`
when `/review` aggregates across all axes.

Refs REQ-008-01, REQ-008-05 (issue #1934).

<!-- vendor-portability: declared. This review axis cites ADRs under .agents/architecture/, the model policy under .agents/governance/, and the output schema under .agents/schemas/ (all upstream-only and reference-only; the file states inline that vendored installs do not ship the schema, so the JSON contract is documented inline). The verdict parser at .claude/lib/ai_review_common/verdict.py ships in the vendor install and works. None of these block the axis. Issue #2050. -->
