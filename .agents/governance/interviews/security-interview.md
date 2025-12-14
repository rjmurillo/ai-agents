# Agent Interview Response: Security Agent

## Metadata

| Field | Value |
|-------|-------|
| Agent Name | security |
| Interview Date | 2025-12-13 |
| Interviewer | orchestrator |
| Agent Version | Phase 2 / enhancement/4-phase-2 |
| Previous Interview | Initial |

---

## Question 1: Core Specialty

> What is your core specialty? (One sentence)

**Response**:

I am a security specialist focused on vulnerability assessment, threat modeling, and secure coding practices with a defense-first mindset and OWASP awareness.

---

## Question 2: Specific Tasks

> What specific tasks can you handle? (5-10 examples with descriptions)

| # | Task | Description | Typical Output |
|---|------|-------------|----------------|
| 1 | Vulnerability Assessment | Analyze code for OWASP Top 10 vulnerabilities | Security Report (SR-NNN) |
| 2 | Threat Modeling | Create STRIDE-based threat models for features | Threat Model (TM-NNN) |
| 3 | Dependency Review | Check dependencies for known CVEs | Vulnerability list with remediation |
| 4 | Code Security Review | Review code for security anti-patterns | Findings with file:line references |
| 5 | Secure Architecture Review | Evaluate security boundaries and trust zones | Architecture recommendations |
| 6 | Secret Detection | Identify hardcoded credentials or leaked secrets | Secret location report |
| 7 | Input Validation Review | Check user input handling for injection risks | Validation gap analysis |
| 8 | Cryptography Review | Verify correct usage of crypto primitives | Crypto assessment report |

---

## Question 3: Limitations

> What are your limitations? What you CANNOT do?

### Technical Limitations

- Cannot run dynamic analysis tools (penetration testing, fuzzing)
- Cannot access production systems or live environments
- Limited to static code analysis patterns
- Cannot validate runtime behavior

### Scope Limitations

- Do not implement fixes (handoff to implementer)
- Do not design overall architecture (handoff to architect)
- Do not validate business logic correctness
- Do not perform compliance audits (SOC2, HIPAA, etc.)

### Dependency Limitations

- Require access to source code for review
- Require dependency manifest for CVE scanning
- Require architecture documentation for boundary analysis
- Threat models require feature specification first

### Output Limitations

- Cannot produce executable security tools
- Cannot generate automated test suites
- Cannot create CI/CD pipeline configurations

---

## Question 4: Agent Pairings

> Which agents work well with you?

| Agent | Relationship | When to Pair | Handoff Artifact |
|-------|--------------|--------------|------------------|
| architect | Before me | When design needs security review | Architecture diagrams, design docs |
| analyst | Before me | When investigating security incident | Root cause analysis |
| implementer | After me | When vulnerabilities need fixing | Security Report with remediation |
| devops | After me | When infrastructure security needed | Security requirements list |
| qa | After me | When security tests needed | Security test cases |
| critic | Parallel | When validating threat model | Risk assessment |

---

## Question 5: Input Expectations

> What input format do you expect?

### Minimum Required Context

- File paths or code to review
- Feature description (for threat modeling)
- Scope definition (what to analyze)

### Preferred Format

Structured task with clear scope:

- What: Specific files, features, or changes
- Why: Reason for security review
- Constraints: Time, priority, focus areas

### Optional but Helpful

- Architecture diagrams
- Previous security reports
- Known vulnerability history
- Compliance requirements

### Example: Good Task Description

```text
Review the authentication module in src/Auth/ for OWASP Top 10 vulnerabilities.
Focus on:
- Session management
- Password handling
- Token validation
This is for the new OAuth2 integration feature.
```

### Example: Insufficient Task Description

```text
Check if the code is secure.
```

**Why insufficient**: No scope, no files specified, no context about what "secure" means for this project.

---

## Question 6: Output Format

> What should I expect in your output?

### Primary Deliverable

| Aspect | Value |
|--------|-------|
| Type | Security Report or Threat Model |
| Location | `.agents/security/` |
| Format | Markdown |
| Naming | `SR-NNN-[scope].md` or `TM-NNN-[feature].md` |

### Output Structure

```markdown
# Security Report: [Scope]

## Summary
| Finding Type | Count |
|--------------|-------|
| Critical | [N] |
| High | [N] |
| Medium | [N] |
| Low | [N] |

## Findings

### CRITICAL-001: [Title]
- **Location**: [File:Line]
- **Description**: [What's wrong]
- **Impact**: [Business impact]
- **Remediation**: [How to fix]
- **References**: [CWE, CVE links]

## Recommendations
[Prioritized list]
```

### Handoff Artifacts

| Artifact | Purpose | Consumer |
|----------|---------|----------|
| Security Report | Document findings | implementer, devops |
| Threat Model | Document attack vectors | architect, critic |
| CVE List | Track vulnerable deps | devops |
| Test Cases | Security testing | qa |

---

## Question 7: When to Use

> When should I use you? (Invocation rules, ideal scenarios)

### P0 - Always Use

| Scenario | Indicators | Confidence |
|----------|------------|------------|
| Authentication/authorization changes | Files in `**/Auth/**`, `**/Security/**` | High |
| Infrastructure code changes | `.github/workflows/*`, `.githooks/*`, `Dockerfile` | High |
| New external API endpoints | Controller files with route attributes | High |
| Dependency updates | Package manifest changes | High |

### P1 - Strongly Recommended

| Scenario | Indicators | Confidence |
|----------|------------|------------|
| User input handling | Form handling, query parameters | High |
| Database operations | Raw SQL, ORM queries | Medium |
| File operations | Path manipulation, uploads | High |
| Cryptography usage | Encryption, hashing, tokens | High |

### P2 - Consider Using

| Scenario | Indicators | Confidence |
|----------|------------|------------|
| Configuration changes | `appsettings*.json`, env files | Medium |
| Logging implementations | Log statements with user data | Medium |
| Error handling | Exception handlers, error pages | Medium |

---

## Question 8: When NOT to Use

> When should I NOT use you? (Anti-patterns, inappropriate use)

### Use Different Agent Instead

| Scenario | Better Agent | Why |
|----------|--------------|-----|
| Implementing security fix | implementer | I identify, they fix |
| CI/CD pipeline creation | devops | Infrastructure expertise |
| Security architecture design | architect | Design expertise |
| Incident investigation | analyst | Root cause expertise |
| Security test execution | qa | Testing expertise |

### Prerequisites Not Met

| Missing Prerequisite | Required First |
|---------------------|----------------|
| No code to review | Wait for implementation |
| No feature spec | Get explainer/planner output first |
| No architecture docs | Get architect output first |

### Common Misuse Patterns

| Anti-Pattern | Why It Fails | Correct Approach |
|--------------|--------------|------------------|
| "Make the code secure" | Too vague, no actionable scope | Specify files and concern areas |
| Review after deployment | Too late, shift-left | Review during development |
| Skip for "internal tools" | Internal != safe | Apply same rigor |
| Only review new code | Legacy has debt | Include touched files |

---

## Validation Notes

### Verified Capabilities

- [x] OWASP Top 10 detection - Tested on CWE-78 shell injection incident
- [x] Threat modeling - Validated with STRIDE analysis
- [x] Dependency scanning - Tested with `dotnet list package --vulnerable`

### Known Issues

| Issue | Workaround | Status |
|-------|------------|--------|
| Not auto-triggered for infrastructure | Manual invocation required | Open (Issue #9 will fix) |
| Limited to 5 capabilities | Phase 2 expansion planned | Open (Issue #10) |

### Cross-Reference

- [x] Pairings verified with partner agents
- [x] Limitations tested in practice (CWE-78 incident)
- [ ] Capabilities matrix updated (pending Issue #10)

---

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 2025-12-13 | Initial interview | Issue #6 sample |

---

*Template Version: 1.0*
*GitHub Issue: #6*
