# CodeRabbit Skills

**Created**: 2025-12-23 (consolidated from 3 memories)
**Sources**: PR #20 analysis, CodeRabbit AI learnings export, multi-agent retrospective
**Skills**: 12

---

## Part 1: Configuration Strategy

**Problem**: 66% noise ratio (33% Trivial + 33% Minor issues). Author spent 67% of review time dismissing noise.

**Root Causes**:
- `assertive` profile duplicates checks handled by automated tools
- Sparse checkout causes false positives for `.agents/` files
- No severity threshold configuration available

**Solution**: Tiered enforcement model

| Tier | Tool | Focus |
|------|------|-------|
| Primary | Automated tooling | `.markdownlint-cli2.yaml`, `dotnet format`, pre-commit hooks |
| Secondary | CodeRabbit (`chill`) | Logic errors, security, architecture |
| Critical | Security agent | Mandatory for infrastructure changes |

---

## Part 2: Key Configuration Settings

**No Severity Threshold**: CodeRabbit does NOT expose severity filtering. Use these controls:

| Control | Effect |
|---------|--------|
| `profile: chill` | Reduces nitpicky feedback (vs `assertive`) |
| `path_instructions` with IGNORE | Most effective noise reduction |
| `markdownlint: enabled: false` | Prevents duplicate linting |
| `path_filters` | Exclude `.agents/**`, `.serena/**`, generated files |

**Effective path_instructions Pattern**:

```yaml
path_instructions:
  - path: "**/*.cs"
    instructions: |
      FOCUS ON: Security, logic errors, race conditions
      IGNORE: style (dotnet format), naming (analyzers), XML docs

  - path: ".github/workflows/**"
    instructions: |
      Profile: ASSERTIVE - security-critical infrastructure
      Flag: Unquoted variables, injection, missing error handling
```

**Estimated Impact**: ~60% noise reduction with optimized configuration.

---

## Part 3: False Positive Patterns

### Skill-CodeRabbit-001: MCP Tool Path Case Sensitivity

**Statement**: MCP tool paths (`github/*`, `cloudmcp-manager/*`) are case-sensitive. Don't suggest capitalizing to "GitHub".

**Evidence**: PR #15 | **Atomicity**: 95%

### Skill-CodeRabbit-002: Template Bracket Placeholders

**Statement**: `[List of...]` in agent templates are runtime placeholders, not incomplete docs.

**Evidence**: PR #15 | **Atomicity**: 93%

### Skill-CodeRabbit-003: Infrastructure Naming Avoids Spaces

**Statement**: Infrastructure files don't need space-handling code. Naming conventions prevent spaces.

**Evidence**: PR #57 | **Atomicity**: 90%

### Skill-CodeRabbit-004: Expression Injection Labeling

**Statement**: "VULNERABLE" labels on `${{ }}` echo statements are accurate, not hyperbolic.

**Evidence**: PR #57 | **Atomicity**: 95%

### Skill-CodeRabbit-005: MCP Tool Duplicated Segments

**Statement**: `mcp__cloudmcp-manager__commicrosoftmicrosoft-learn...` - repeated segments follow MCP naming convention.

**Evidence**: PR #32 | **Atomicity**: 92%

### Skill-CodeRabbit-006: Generated Files Omit Edit Warnings

**Statement**: Generated `.agent.md` files omit "DO NOT EDIT" headers - AI agents consume these and human warnings add noise.

**Evidence**: PR #43 | **Atomicity**: 90%

### Skill-CodeRabbit-007: Analyst vs Impact Analysis

**Statement**: Analyst saves to `.agents/analysis/`. Impact analysis (5 specialists) saves to `.agents/planning/impact-analysis-*.md`.

**Evidence**: PR #46 | **Atomicity**: 95%

### Skill-CodeRabbit-008: Nested Code Fence Syntax

**Statement**: Outer fence needs more backticks than inner. 4-backtick outer with 3-backtick inner is correct CommonMark.

**Evidence**: PR #43 | **Atomicity**: 88%

---

## Part 4: Markdownlint Integration

**Auto-Suppressed Rules**: MD004, MD012, MD013, MD025, MD026, MD032, MD033

**Best Practice**: Disable CodeRabbit's markdownlint when project has `.markdownlint-cli2.yaml`:

```yaml
tools:
  markdownlint:
    enabled: false  # Already enforced by .markdownlint-cli2.yaml
```

**Note**: 4 duplicate learnings about "defer to `.markdownlint-cli2.yaml`" already covered in `skills-linting`.

---

## Part 5: Recommended Configuration

```yaml
# .coderabbit.yaml - Noise Reduction Strategy
reviews:
  profile: chill  # Not assertive
  high_level_summary: false
  poem: false
  
  path_filters:
    - '!.agents/**'
    - '!.serena/**'
    - '!**/obj/**'
    - '!**/bin/**'
    - '!**/*.Designer.cs'
    - '!**/*.generated.cs'
  
  path_instructions:
    - path: '.github/workflows/**'
      instructions: >-
        Profile: ASSERTIVE. Review for: auth, credentials, injection, 
        race conditions. Flag: unquoted variables, missing error handling.
    
    - path: '**/*.cs'
      instructions: >-
        FOCUS: Logic errors, security, OWASP Top 10.
        IGNORE: style, formatting, naming (handled by tools).

tools:
  markdownlint:
    enabled: false
```

---

## Quick Reference

| Skill | When to Dismiss CodeRabbit Comment |
|-------|-----------------------------------|
| 001 | MCP paths flagged for capitalization |
| 002 | Bracket placeholders flagged as incomplete |
| 003 | Missing space-handling in infrastructure |
| 004 | Security labels flagged as too strong |
| 005 | MCP tool names flagged for duplication |
| 006 | Missing "DO NOT EDIT" in generated files |
| 007 | Confusion about analyst vs impact analysis |
| 008 | Nested code fences flagged as errors |

## Success Metrics

| Metric | Before | Target |
|--------|--------|--------|
| Trivial + Minor comments | 66% | ~15% |
| False positives per PR | 4-5 | 0-1 |
| Signal-to-noise ratio | 34% | >80% |

## Related

- `.coderabbit.yaml` - Configuration file
- `skills-linting` - Markdownlint patterns (deferred to)
- `.agents/architecture/ADR-002-coderabbit-config.md`
