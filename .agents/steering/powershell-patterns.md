---
name: PowerShell Patterns
applyTo: "**/*.ps1,**/*.psm1"
priority: 8
version: 0.1.0
status: placeholder
---

# PowerShell Patterns Steering

**Status**: Placeholder for Phase 4 implementation

## Scope

**Applies to**: `**/*.ps1`, `**/*.psm1`

## Purpose

This steering file will provide PowerShell coding standards and patterns for implementer agent.

## Planned Content (Phase 4)

### Guidelines
- Approved verbs (Get-, Set-, New-, Remove-, etc.)
- Parameter conventions and validation
- Error handling (ErrorActionPreference, try/catch)
- Pipeline usage and best practices
- Module structure and exports
- Comment-based help standards

### Patterns
- Advanced function template with CmdletBinding
- Parameter validation attributes
- Pipeline input handling
- Progress reporting for long operations
- Configuration management

### Anti-Patterns
- Using aliases in scripts
- Suppressing errors without handling
- Not using approved verbs
- Missing parameter validation
- Hardcoded paths

### Examples
- Well-structured functions
- Proper error handling
- Pipeline-aware cmdlets

---

*This is a placeholder file. Content will be added in Phase 4: Steering Scoping*
