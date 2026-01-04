# ADR-005 Amendment 001: SkillForge Python Scripts Exception

**Status**: APPROVED
**Date**: 2026-01-04
**Approved By**: Owner (Option A selected)
**Parent ADR**: [ADR-005: PowerShell-Only Scripting Standard](./ADR-005-powershell-only-scripting.md)
**PR**: #760

---

## Context and Problem Statement

PR #760 introduces SkillForge, a skill packaging and validation system that includes Python scripts:

- `.claude/skills/SkillForge/scripts/package_skill.py`
- `.claude/skills/SkillForge/scripts/quick_validate.py`
- `.claude/skills/SkillForge/scripts/validate-skill.py`
- `.claude/skills/SkillForge/scripts/triage_skill_request.py`

This violates [ADR-005: PowerShell-Only Scripting Standard](./ADR-005-powershell-only-scripting.md), which states:

> **Exceptions: NONE**. All scripts must be PowerShell.

**Key Question**: Should SkillForge scripts be exempted from ADR-005, or must they be converted to PowerShell?

---

## Decision Drivers

### Factors Favoring Exception

1. **Tool Portability**: SkillForge is designed for distribution to the broader Claude Code community, where Python may be more universally available than PowerShell
2. **Minimal Footprint**: Skill packaging is a development-time tool, not CI/CD infrastructure
3. **Upstream Dependency**: SkillForge may align with Anthropic's Claude Code tooling expectations (Python-first)
4. **YAML Parsing**: Python's `yaml` library is more mature than PowerShell's YAML handling
5. **Regex Safety**: Python's regex is well-tested for frontmatter validation

### Factors Against Exception

1. **Consistency**: Creates precedent for "optional" adherence to PowerShell standard
2. **Testing Fragmentation**: Requires pytest instead of Pester (violates ADR-005 rationale)
3. **Dependencies**: Adds Python runtime requirement for skill development
4. **Token Waste Risk**: Agents may use this as justification to generate Python elsewhere
5. **PowerShell Capability**: All SkillForge functionality is implementable in PowerShell

---

## Proposed Amendment

### Option A: Approve Exception (Conditional)

**Scope**: Allow Python scripts ONLY within `.claude/skills/SkillForge/scripts/`

**Conditions**:
1. SkillForge scripts MUST NOT be part of CI/CD pipelines
2. SkillForge scripts MUST include path validation to prevent security issues (DONE in PR #760)
3. SkillForge scripts MUST be tested before distribution
4. Future skills MAY NOT use this as precedent without new ADR amendment

**Rationale**:
- SkillForge is a developer tool, not infrastructure
- Skill distribution benefits from Python portability
- Narrow scope prevents slippery slope

**ADR-005 Update Required**:

```markdown
### Exceptions

1. **SkillForge Developer Tools** (`.claude/skills/SkillForge/scripts/*.py`):
   - Purpose: Skill packaging and validation for distribution
   - Justification: Portability for skill sharing across Claude Code community
   - Scope: Development tools only, not CI/CD infrastructure
   - Security: Path validation required (CWE-22 prevention)
   - Status: Approved by [Amendment 001](./ADR-005-AMENDMENT-001-skillforge-python-exception.md)
```

### Option B: Reject Exception (PowerShell Conversion)

**Requirement**: Convert all SkillForge Python scripts to PowerShell

**Implementation**:
- `package_skill.py` → `New-SkillPackage.ps1`
- `quick_validate.py` → `Test-SkillQuick.ps1`
- `validate-skill.py` → `Test-Skill.ps1`
- `triage_skill_request.py` → `Invoke-SkillTriage.ps1`

**Effort Estimate**: 200-300 lines PowerShell, ~2-3 hours conversion

**Pros**:
- ✅ Complete ADR-005 compliance
- ✅ Consistent testing with Pester
- ✅ No Python dependency

**Cons**:
- ❌ Less portable for skill distribution
- ❌ YAML parsing less mature in PowerShell
- ❌ Requires refactoring current PR

---

## Recommendation

**Option A: Approve Exception with Narrow Scope**

**Justification**:

1. **Intent vs Letter**: ADR-005's intent is to prevent infrastructure fragmentation. SkillForge is a developer tool, not infrastructure.

2. **Community Benefit**: Skill distribution across Claude Code community benefits from Python portability.

3. **Security Addressed**: PR #760 already added path validation to prevent CWE-22 vulnerabilities flagged by CodeQL.

4. **Narrow Scope**: Limiting exception to `.claude/skills/SkillForge/scripts/*.py` prevents precedent creep.

5. **Reversible**: If Python dependency becomes problematic, conversion to PowerShell remains feasible.

**Risks**:

1. **Precedent Risk**: Agents may cite this as justification for Python elsewhere.
   - **Mitigation**: Explicit scope limitation in ADR update; agents must reference exception criteria.

2. **Testing Fragmentation**: Requires pytest for SkillForge.
   - **Mitigation**: SkillForge testing is isolated, not part of main CI/CD.

---

## Decision

**APPROVED: Option A - Narrow Python Exception**

**Approved**: 2026-01-04 by repository owner

**Scope**: `.claude/skills/SkillForge/scripts/*.py` only

**Next Steps**:
1. ✅ Path validation implemented (commit 1410ee2)
2. ✅ Security review complete (CodeQL + gemini-code-assist)
3. Update ADR-005 with exception language in future PR

---

## References

- [ADR-005: PowerShell-Only Scripting Standard](./ADR-005-powershell-only-scripting.md)
- [PR #760](https://github.com/rjmurillo/ai-agents/pull/760): SkillForge implementation
- CodeQL Security Alerts: 6 path traversal issues (fixed in commit 1d07eb5)
- rjmurillo-bot Comment: "PR adds new Python files when PowerShell is required"
