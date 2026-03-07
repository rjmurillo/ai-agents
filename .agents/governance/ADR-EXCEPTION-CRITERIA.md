# ADR Exception Criteria

> **Status**: Active
> **Version**: 1.0
> **Last Updated**: 2026-02-19
> **Related**: ADR-005, ADR-042, PR #908 Retrospective

## Purpose

Define criteria and process for evaluating ADR exceptions. Exceptions should be rare and justified. This framework prevents tactical violations disguised as strategic exceptions.

## Chesterton's Fence Principle

Before removing or bypassing a rule, understand why it exists.

> "Do not remove a fence until you know why it was put up." - G.K. Chesterton

This principle requires understanding the original rationale before proposing exceptions. Rules exist for reasons that may not be immediately obvious.

## Required Analysis Before Exception

An exception request MUST document:

### 1. Why Does the Rule Exist?

- [ ] Original rationale identified (read the ADR)
- [ ] Problem the ADR solved documented
- [ ] Historical context understood

Example:

```markdown
**Rule**: ADR-005 requires PowerShell-only scripting.
**Original Rationale**: Agents wasted 830+ lines generating bash code that was
later deleted. Standardizing on PowerShell eliminates this waste and keeps
testing consolidated on Pester.
```

### 2. Impact If Exception Is Granted

- [ ] Technical debt created by exception documented
- [ ] Downstream effects on testing, CI, maintenance identified
- [ ] Precedent risk assessed (will others request similar exceptions?)
- [ ] Reversibility plan defined

Example:

```markdown
**Debt Created**: Python hooks require pip dependencies separate from PowerShell ecosystem.
**Testing Impact**: Tests must run in both Pester and pytest.
**Precedent Risk**: Low - narrow scope (hooks directory only).
**Reversibility**: Port to PowerShell if Anthropic releases PowerShell SDK.
```

### 3. Alternatives Tried

- [ ] At least two alternatives documented
- [ ] Why each alternative failed explained
- [ ] Evidence provided (not just assertions)

Example:

```markdown
**Alternative 1**: Use PowerShell with HTTP calls to Anthropic API.
**Result**: Failed. 200+ lines of code for one API call. No retry logic. No
streaming support. Fragile.

**Alternative 2**: Wait for official PowerShell SDK.
**Result**: Failed. No roadmap for PowerShell SDK from Anthropic.

**Alternative 3**: Use Python with Anthropic SDK (proposed exception).
**Result**: 15 lines of code. Full SDK support. Production-ready.
```

## Decision Criteria

| Criterion | Threshold | Evidence |
|-----------|-----------|----------|
| Rule understanding | Must articulate original rationale | Quote from ADR |
| Alternatives exhausted | Minimum 2 alternatives tried | Failure evidence |
| Scope limitation | Narrowest possible exception | Explicit boundary |
| Reversibility | Path to undo exception | Documented plan |
| Precedent control | No open-ended language | Explicit exclusions |

## Exception Classification

### Strategic Exception (Justified)

- Root cause is permanent (external constraint)
- Exception has narrow, documented scope
- Reversibility plan exists
- No reasonable alternative

**Example**: Using Python for Anthropic SDK because no PowerShell SDK exists and HTTP calls are inadequate.

### Tactical Violation (Not Justified)

- Root cause is convenience or time pressure
- Scope is vague or expanding
- No reversibility consideration
- Alternatives not seriously attempted

**Example**: Using Python "because it's faster to write" without attempting PowerShell implementation.

## Exception Template

Use this template when proposing ADR exceptions:

```markdown
## ADR Exception Request

**ADR**: [ADR-NNN]
**Scope**: [Specific paths/files affected]
**Requested By**: [Agent/Author]
**Date**: [YYYY-MM-DD]

### Chesterton's Fence Analysis

#### Why Does the Rule Exist?

[Document original rationale from ADR]

#### What Breaks Without the Rule?

[Document what the rule prevents]

### Alternatives Attempted

| Alternative | Attempt | Outcome | Evidence |
|-------------|---------|---------|----------|
| [Option 1] | [What tried] | [Failed/Partial] | [Link/commit] |
| [Option 2] | [What tried] | [Failed/Partial] | [Link/commit] |

### Exception Details

**Scope Boundary**: [Exact files/paths where exception applies]
**What This Exception Does NOT Permit**: [Explicit exclusions]
**Reversibility Plan**: [How to undo if circumstances change]
**Expiration**: [Review date or trigger condition]

### Impact Assessment

**Technical Debt Created**: [Quantified impact]
**Testing Impact**: [How testing changes]
**Maintenance Impact**: [Who maintains, how]
**Precedent Control**: [Why this won't open floodgates]

### Approval

- [ ] Architect review complete
- [ ] Scope is narrowest possible
- [ ] Alternatives documented with evidence
- [ ] Reversibility plan defined
- [ ] Added to ADR as amendment (not new exception ADR)
```

## Process

1. **Author** completes exception template
2. **Architect** validates Chesterton's Fence analysis
3. **Architect** verifies alternatives were genuinely attempted
4. If approved, **Architect** adds exception to original ADR as amendment
5. **Retrospective agent** captures pattern for future reference

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| **Vague scope** | "Python may be used when needed" | Define exact paths/conditions |
| **Missing rationale** | "It's easier this way" | Document why the rule exists |
| **Single alternative** | "PowerShell doesn't work" | Try at least two approaches |
| **No reversibility** | Permanent exception by default | Define exit conditions |
| **Expanding scope** | Exception creeps to new areas | Review and reauthorize |

## Example: PR #908 Python Exception (Good)

This exception followed the framework correctly:

1. **Rule Understanding**: ADR-005 exists because bash/Python generation wasted tokens.

2. **Impact Assessment**: Python in hooks directory only. Separate from CI/CD. No precedent for scripts directory.

3. **Alternatives**:
   - PowerShell HTTP calls: 200+ lines, no retry, no streaming
   - Wait for SDK: No roadmap exists
   - Python SDK: 15 lines, full support

4. **Scope**: `.claude/hooks/**/*.py` only

5. **Reversibility**: Port to PowerShell if SDK becomes available

## References

- [ADR-005: PowerShell-Only Scripting](../architecture/ADR-005-powershell-only-scripting.md)
- [ADR-042: Python Migration Strategy](../architecture/ADR-042-python-migration-strategy.md)
- [PR #908 Retrospective](../retrospective/2026-01-15-pr-908-comprehensive-retrospective.md) (lines 1280-1285)
- Chesterton's Fence: G.K. Chesterton, "The Thing" (1929), Chapter 4

## Validation

Architect agent MUST verify before approving exception:

- [ ] Author articulated original rule rationale
- [ ] At least two alternatives documented with failure evidence
- [ ] Scope is explicitly bounded (paths, files, conditions)
- [ ] Reversibility plan exists
- [ ] Exception added as ADR amendment (not standalone document)
