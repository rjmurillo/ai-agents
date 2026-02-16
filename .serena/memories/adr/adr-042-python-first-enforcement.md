# ADR-042 Python-First Enforcement

**Importance**: CRITICAL  
**Date**: 2026-01-19  
**Session**: 14  
**Issues**: #756

## The Rule

**ADR-042 supersedes ADR-005.** New scripts MUST be Python (`.py`), not PowerShell (`.ps1`).

## Application

### Issue #756: Security Agent Detection Gaps

Original plan specified PowerShell scripts:
- `Invoke-SecurityRetrospective.ps1`
- `Invoke-PreCommitSecurityCheck.ps1`

Implemented as Python per ADR-042:
- `scripts/security/invoke_security_retrospective.py`
- `scripts/security/invoke_precommit_security.py`

### Rationale

1. **ADR-042 post-dates plan**: Accepted 2026-01-17, plan written earlier
2. **Better MCP integration**: MCP SDK is Python, Forgetful MCP requires Python
3. **pytest infrastructure**: Already planned in ADR-042 Phase 1
4. **CodeQL coverage**: Better support for Python per ADR-042

## Pattern

When plan specifies PowerShell but work is new:
1. Check ADR-042 acceptance date
2. If plan pre-dates ADR-042, use Python
3. Clarify with user if uncertain
4. PowerShell is grandfathered for EXISTING scripts only

## Related

- ADR-042: Python-First Scripting Standard
- ADR-005: PowerShell-only (superseded by ADR-042)
- Security benchmarks: Converted from .ps1 to .py per ADR-042
