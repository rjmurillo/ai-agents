# Session 122: ADR-036 Security Review

**Date**: 2026-01-01
**Agent**: Security
**Task**: Independent security review of ADR-036 (Two-Source Agent Template Architecture)

## Session Protocol Compliance

- [x] Serena initialized (`initial_instructions`)
- [x] HANDOFF.md read (read-only reference)
- [x] Session log created
- [x] PROJECT-CONSTRAINTS.md read

## Objective

Provide security review of ADR-036 as part of Phase 1 (Independent Review) of the ADR review process.

## Materials Reviewed

1. ADR-036: Two-Source Agent Template Architecture
2. `build/Generate-Agents.ps1` - Generation script
3. `build/Generate-Agents.Common.psm1` - Shared functions module
4. `.githooks/pre-commit` (lines 475-545) - Agent generation trigger
5. `.github/workflows/validate-generated-agents.yml` - CI validation
6. `.github/workflows/drift-detection.yml` - Drift detection workflow
7. Serena memory: `pattern-agent-generation-three-platforms`

## Security Analysis

### Threat Surface

1. **Build Pipeline Security**
   - Generator script (`Generate-Agents.ps1`) processes template files and writes outputs
   - Pre-commit hook executes PowerShell with `-ExecutionPolicy Bypass`
   - CI workflow regenerates and validates

2. **Platform Drift Risk**
   - Claude agents (`src/claude/`) are manually maintained
   - Copilot CLI and VS Code agents are auto-generated
   - Shared content requires dual updates (two sources)

3. **Supply Chain Considerations**
   - Template files are source of truth for 2/3 platforms
   - No external dependencies in generation pipeline
   - Local-only generation (no remote code execution)

### Security Controls Observed

1. **Path Traversal Prevention** (CWE-22)
   - `Test-PathWithinRoot` function validates output paths stay within repo root
   - Implements directory separator append to prevent prefix attacks

2. **Symlink Attack Prevention** (MEDIUM-002)
   - Pre-commit hook checks for symlinks before executing scripts
   - Generated file staging includes symlink rejection
   - Defense-in-depth pattern applied consistently

3. **CI Validation**
   - `validate-generated-agents.yml` regenerates and compares to committed files
   - Drift detection workflow monitors Claude vs template sync

## Findings

See: `.agents/security/SR-036-adr-architecture-review.md`

## Outcome

Security review complete. Returned to orchestrator/ADR review process.
