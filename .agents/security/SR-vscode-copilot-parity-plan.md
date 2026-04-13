# Security Report: VSCode Copilot Parity Plan

**Analyst**: Security
**Date**: 2026-01-14
**Scope**: `.agents/planning/claude-compat/vscode-copilot-parity-plan.md`
**Status**: [COMPLETE]

## Summary

| Finding Type | Count |
|--------------|-------|
| Critical | 0 |
| High | 2 |
| Medium | 3 |
| Low | 2 |

## Findings

### HIGH-001: Insufficient License Verification Due Diligence

- **Location**: Phase 0, Line 154
- **CWE**: CWE-1104 (Use of Unmaintained Third Party Components)
- **Risk Score**: 7/10
- **Description**: The 30-minute decision gate for license research is inadequate for legal risk mitigation. The plan states: "If origins cannot be determined after 30 minutes of research, proceed with 'Unknown origin, used under assumption of MIT compatibility per project license'". This assumption creates legal exposure.
- **Impact**: Potential copyright infringement if agents contain proprietary/copyrighted content. Legal liability for redistribution of non-MIT licensed content.
- **Evidence**: Agents `debug.md`, `janitor.md`, `prompt-builder.md`, `technical-writer.md` have "Unknown" origins per the plan's agent origin table (lines 96-106).

**Remediation**:

1. Extend research phase to minimum 4 hours with documented search trails
2. If origin cannot be determined, DO NOT include in templates; create original versions instead
3. Add legal review gate: No agent with unknown origin proceeds without legal signoff
4. Document research methodology and results in `THIRD-PARTY-LICENSES.txt`

### HIGH-002: Agent Content May Expose Internal References

- **Location**: Phase 1-2, copying agents from `.claude/agents/` to `src/`
- **CWE**: CWE-200 (Exposure of Sensitive Information)
- **Risk Score**: 6/10
- **Description**: Agents in `.claude/agents/` may contain internal references that violate user-facing content restrictions (AGENTS.md lines 533-549). The plan does not include validation steps to detect and remove these before templating.
- **Impact**: End users receive agent files containing internal PR numbers, issue references, session identifiers, or internal paths that are meaningless or confusing.
- **Evidence**:
  - `technical-writer.md` line 165 references external GitHub URL (safe)
  - `prompt-builder.md` contains Claude-specific tool references (`context7`, `microsoft.docs.mcp`) that need removal per plan
  - No systematic scan for internal references is included in plan tasks

**Remediation**:

1. Add M1-T9: "Scan all copied agents for internal references"
2. Create validation script: `scripts/Validate-UserFacingContent.ps1`
3. Add acceptance criteria: "No internal PR/Issue/Session references present"
4. Block merge if validation fails

### MEDIUM-001: MCP Server Configuration May Leak Tool References

- **Location**: Phase 2, template creation (lines 188-193)
- **CWE**: CWE-209 (Error Message Information Leak)
- **Risk Score**: 5/10
- **Description**: Plan lists MCP tool patterns to remove (`mcp__serena__*`, `mcp__forgetful__*`) but does not comprehensively audit for all MCP patterns that may expose internal tool configurations.
- **Impact**: Templates may contain MCP tool syntax that fails silently or exposes internal tooling names to users.
- **Evidence**:
  - `prompt-builder.md` tools list includes `terraform`, `Microsoft Docs`, `context7`
  - `janitor.md` tools list includes `microsoft.docs.mcp`, `github`, `vscode/*` prefixed tools

**Remediation**:

1. Create exhaustive MCP pattern list for removal:
   - `mcp__*` (double underscore MCP format)
   - `vscode/*` (VSCode-specific tool prefixes)
   - Internal MCP server names
2. Add M2-T0: "Audit all agent tool lists for MCP patterns"
3. Document allowed tool patterns in `templates/PLATFORM-LIMITATIONS.md`

### MEDIUM-002: Installer Path Handling May Allow Directory Traversal

- **Location**: `scripts/install.ps1` lines 213-216, `scripts/lib/Install-Common.psm1`
- **CWE**: CWE-22 (Improper Limitation of a Pathname to a Restricted Directory)
- **Risk Score**: 5/10
- **Description**: `Resolve-DestinationPath` function uses `InvokeCommand.ExpandString` to expand path expressions. While paths are validated afterward, malicious Config.psd1 modifications or user input could potentially escape intended directories.
- **Impact**: Files could be written outside intended installation directories if Config.psd1 is tampered with.
- **Evidence**:
  - Line 133 in Install-Common.psm1: `$ResolvedPath = $ExecutionContext.InvokeCommand.ExpandString($PathExpression)`
  - No explicit path traversal prevention (e.g., checking for `..` sequences)
  - RepoPath is resolved via `Resolve-Path` (line 215) but not sanitized for traversal

**Remediation**:

1. Add path traversal validation to `Resolve-DestinationPath`:

   ```powershell
   if ($ResolvedPath -match '\.\.[/\\]') {
       throw "Path traversal detected: $ResolvedPath"
   }
   ```

2. Validate resolved paths are within expected parent directories
3. Add Pester test: `Install-Common.Tests.ps1` with traversal test cases

### MEDIUM-003: Remote Execution Downloads Unauthenticated Content

- **Location**: `scripts/install.ps1` lines 98-117
- **CWE**: CWE-494 (Download of Code Without Integrity Check)
- **Risk Score**: 5/10
- **Description**: Remote installation via `iex` downloads installer components from GitHub without integrity verification (no checksum or signature validation).
- **Impact**: Man-in-the-middle attack could inject malicious code during remote installation. Supply chain compromise if GitHub raw content is modified.
- **Evidence**:
  - Line 105-106: `$WebClient.DownloadFile(...)` with no hash verification
  - Line 247: `Invoke-RestMethod` for GitHub API with no signature verification

**Remediation**:

1. Generate SHA256 checksums for released versions
2. Create `checksums.sha256` file in each release
3. Verify downloaded files against published checksums:

   ```powershell
   $Hash = (Get-FileHash -Path $File -Algorithm SHA256).Hash
   if ($Hash -ne $ExpectedHash) { throw "Integrity check failed" }
   ```

4. Document that users should prefer local installation for sensitive environments

### LOW-001: Skill Installation Removes Existing Directory Without Backup

- **Location**: `scripts/lib/Install-Common.psm1` lines 607-609
- **CWE**: CWE-379 (Creation of Temporary File in Directory with Insecure Permissions)
- **Risk Score**: 3/10
- **Description**: `Install-SkillFiles` removes existing skill directory before copying new version without creating a backup.
- **Impact**: User modifications to skill files are lost without warning. No rollback capability if installation fails mid-copy.

**Remediation**:

1. Create backup before removal: `$BackupPath = "$SkillDestPath.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"`
2. Only delete backup after successful copy
3. Add `-PreserveBackup` parameter option

### LOW-002: Agent Origin Table Lacks Verification Method

- **Location**: Phase 0, lines 96-106
- **CWE**: CWE-1035 (Use of Components with Known Vulnerabilities - related)
- **Risk Score**: 2/10
- **Description**: The agent origin table marks `adr-generator`, `context-retrieval`, `spec-generator` as "Custom/Internal" without documented verification method.
- **Impact**: Future maintainers cannot verify claims. Audit trail is incomplete.

**Remediation**:

1. Add "Verification Method" column to origin table
2. Document how each origin was determined (git history, author interview, etc.)
3. Include commit SHA or date range for original authorship

## Attack Surface Analysis

| New Surface | Threat Level | Mitigation Required |
|-------------|--------------|---------------------|
| 7 new agent templates | Low | Content validation before templating |
| 2 new prompt files | Low | Same content restrictions as agents |
| Config.psd1 expansion | Medium | Path traversal prevention |
| Remote installer | Medium | Integrity verification |

## Threat Vectors

| Threat | STRIDE Category | Likelihood | Impact | Mitigation |
|--------|-----------------|------------|--------|------------|
| Copyrighted content inclusion | Repudiation | Medium | High | Extended license research |
| Internal reference exposure | Information Disclosure | Medium | Low | Automated content validation |
| Path traversal via config | Tampering | Low | Medium | Input sanitization |
| MITM during remote install | Spoofing | Low | High | Checksum verification |

## Compliance Implications

- **MIT License Compliance**: Plan's 30-minute assumption does not meet due diligence standard
- **User-Facing Content Policy**: No automated enforcement mechanism in plan

## Recommendations (Prioritized)

| Priority | Recommendation |
|----------|----------------|
| P0 | Extend license research to 4+ hours; create original content for unknown-origin agents |
| P1 | Add content validation script for user-facing restrictions |
| P1 | Add path traversal prevention to Resolve-DestinationPath |
| P2 | Add integrity verification for remote installation |
| P2 | Document MCP pattern removal exhaustively |

## Verdict

**[CONDITIONAL]** - Plan may proceed with the following blocking requirements:

1. **Before Phase 0 completion**: Document research methodology for unknown-origin agents. If origin cannot be determined with reasonable confidence, create new original agents instead of copying.
2. **Before Phase 1 completion**: Add M1-T9 validation task for user-facing content restrictions.
3. **Before Phase 4 completion**: Add path traversal validation to installer.

Non-blocking recommendations should be addressed in subsequent iterations.

---

**Security Agent**: Verified 2026-01-14
