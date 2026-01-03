# Security Report: PR #752 Memory System Foundation

**Reviewer**: Security Agent
**Date**: 2026-01-03
**Scope**: All changes in PR #752 (feat/m009-bootstrap-forgetful, commits af3c96d through 4101f25)
**Risk Score**: 4/10 (Low-Medium)
**Verdict**: APPROVED_WITH_CONDITIONS

---

## Executive Summary

| Finding Type | Count |
|--------------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 3 |
| Low | 4 |

The Memory System Foundation PR introduces Claude-Mem export/import infrastructure, research skills, and memory-documentary capabilities. The architecture follows defense-in-depth principles with automatic security review as a blocking gate. Three medium-severity issues require remediation before merge. All high-risk attack vectors have mitigations in place.

---

## Components Reviewed

| Component | Location | Risk Focus |
|-----------|----------|------------|
| Export-ClaudeMemMemories.ps1 | `.claude-mem/scripts/` | Command injection, path traversal |
| Import-ClaudeMemMemories.ps1 | `.claude-mem/scripts/` | Data validation, command injection |
| Export-ClaudeMemDirect.ps1 | `.claude-mem/scripts/` | SQL injection, data exfiltration |
| Export-ClaudeMemFullBackup.ps1 | `.claude-mem/scripts/` | Command injection, data exfiltration |
| Review-MemoryExportSecurity.ps1 | `scripts/` | Pattern completeness, bypass risks |
| research-and-incorporate skill | `.claude/skills/` | Prompt injection |
| memory-documentary command | `.claude/commands/` | Information disclosure |
| ADR-037 | `.agents/architecture/` | Design security |
| Forgetful commands | `.claude/commands/forgetful/` | MCP tool abuse |

---

## Findings

### MEDIUM-001: SQL Injection via Project Parameter

**Location**: `.claude-mem/scripts/Export-ClaudeMemDirect.ps1:100-108`
**CWE**: CWE-89 (SQL Injection)
**CVSS**: 5.5 (Medium)

**Description**: The `$Project` parameter is interpolated directly into SQLite query strings without parameterization.

**Vulnerable Code**:

```powershell
$ObsFilter = if ($Project) { "WHERE o.project = '$Project'" } else { "" }
$SummaryFilter = if ($Project) { "WHERE ss.project = '$Project'" } else { "" }
$SessionFilter = if ($Project) { "WHERE project = '$Project'" } else { "" }
```

**Attack Vector**: A malicious project name like `ai-agents'; DROP TABLE observations; --` could execute arbitrary SQL.

**Impact**: Data destruction, unauthorized data access. Affects local SQLite database only.

**Remediation**:

```powershell
# Option 1: Validate project name (allow-list)
[ValidatePattern('^[a-zA-Z0-9_-]+$')]
[string]$Project,

# Option 2: Use parameterized queries (preferred if sqlite3 supports)
# Note: sqlite3 CLI has limited parameterization support
```

**Risk Reduction**: Attack requires local CLI access with malicious input. Low exploitability in practice but violates defense-in-depth.

---

### MEDIUM-002: Command Injection via External Process Calls

**Location**: Multiple scripts use `npx tsx` with unsanitized arguments
**CWE**: CWE-78 (OS Command Injection)
**CVSS**: 5.2 (Medium)

**Affected Files**:

| File | Line | Command |
|------|------|---------|
| Export-ClaudeMemMemories.ps1 | 114 | `npx tsx $PluginScript $Query $OutputFile` |
| Import-ClaudeMemMemories.ps1 | 57 | `npx tsx $PluginScript $File.FullName` |
| Export-ClaudeMemFullBackup.ps1 | 57 | `npx tsx $PluginScript @PluginArgs` |

**Description**: Query strings and file paths are passed to external commands without shell escaping. PowerShell's argument passing is safer than shell interpolation but edge cases exist.

**Attack Vector**: A query containing shell metacharacters like `"; rm -rf /; echo "` could cause unintended execution depending on how the TypeScript script parses arguments.

**Mitigations Already Present**:

1. Query comes from user input at session time (low privilege scenario)
2. TypeScript scripts parse arguments directly (not via shell)
3. File paths are generated internally, not user-supplied

**Remediation**:

```powershell
# Validate Query parameter at entry point
[ValidatePattern('^[a-zA-Z0-9\s\-_.,()]+$')]
[string]$Query,

# Or use explicit argument array (already done in FullBackup)
$PluginArgs = @($Query, $OutputPath)
& npx tsx $PluginScript @PluginArgs
```

---

### MEDIUM-003: Incomplete Secret Detection Patterns

**Location**: `scripts/Review-MemoryExportSecurity.ps1:42-77`
**CWE**: CWE-312 (Cleartext Storage of Sensitive Information)
**CVSS**: 4.8 (Medium)

**Description**: The security scanner has 6 pattern categories but misses common secret formats.

**Current Patterns**:

- API Keys/Tokens (4 patterns)
- Passwords/Secrets (4 patterns)
- Private Keys (2 patterns)
- File Paths (3 patterns)
- Database Credentials (5 patterns)
- Email/PII (3 patterns)

**Missing Patterns**:

| Pattern Type | Regex | Risk |
|--------------|-------|------|
| AWS Access Keys | `AKIA[0-9A-Z]{16}` | High |
| Azure Client Secrets | `[a-zA-Z0-9~_.-]{34}` | High |
| Slack Tokens | `xox[baprs]-[0-9a-zA-Z]{10,}` | Medium |
| npm Tokens | `npm_[A-Za-z0-9]{36}` | Medium |
| Base64 encoded secrets | `[A-Za-z0-9+/=]{40,}` | Medium |
| SSH key fingerprints | `SHA256:[A-Za-z0-9+/=]{43}` | Low |
| IP addresses (private) | `(10|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.\d+\.\d+` | Low |

**Remediation**: Add missing patterns to `$SensitivePatterns` hashtable. Consider using established secret detection tools like `gitleaks` or `trufflehog` as fallback.

---

### LOW-001: Path Traversal Not Validated in Import

**Location**: `.claude-mem/scripts/Import-ClaudeMemMemories.ps1:43`
**CWE**: CWE-22 (Path Traversal)
**CVSS**: 3.1 (Low)

**Description**: The import script processes all `.json` files in the memories directory without validating symlinks.

**Code**:

```powershell
$Files = @(Get-ChildItem -Path $MemoriesDir -Filter '*.json' -File)
```

**Attack Vector**: An attacker with write access to `.claude-mem/memories/` could create a symlink to `/etc/passwd` or other sensitive files.

**Mitigations Present**:

1. Symlinks would not parse as valid JSON (fails later)
2. Directory is in git repository (symlinks visible in PR)
3. Import only reads, does not write to linked location

**Remediation**:

```powershell
# Add symlink check
$Files = @(Get-ChildItem -Path $MemoriesDir -Filter '*.json' -File |
    Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint -eq 0 })
```

---

### LOW-002: Memory Export May Contain Sensitive Session Data

**Location**: Export-ClaudeMemDirect.ps1
**CWE**: CWE-200 (Information Exposure)
**CVSS**: 3.5 (Low)

**Description**: Full database exports include all session observations, which may contain sensitive data discussed during Claude Code sessions.

**Attack Vector**: Session observations may inadvertently contain:

- Partial API keys mentioned during debugging
- Database schemas with column names
- Internal file paths from error messages
- Credential patterns in code snippets

**Mitigations Present**:

1. Security scanner runs automatically (blocking gate)
2. Export prompts for manual review
3. Exports are local-only (not uploaded)

**Recommendation**: Add documentation warning about sensitive session data. Consider adding a `--sanitize` flag for production exports.

---

### LOW-003: Ultrathink Extended Thinking May Log Sensitive Analysis

**Location**: `.claude/commands/memory-documentary.md:9`
**CWE**: CWE-532 (Information Exposure Through Log Files)
**CVSS**: 2.8 (Low)

**Description**: The memory-documentary command uses `ultrathink` extended thinking mode, which may generate detailed reasoning logs containing sensitive analysis.

**Code**:

```markdown
> **Note**: This command uses extended thinking (`ultrathink`) for evidence-based analysis.
```

**Risk**: Extended thinking may:

- Log reasoning about security patterns
- Reference sensitive file paths
- Contain analysis of vulnerabilities

**Mitigation**: Extended thinking is local-only in Claude Code. No network transmission of thinking content.

**Recommendation**: Document that ultrathink outputs should not be shared externally without review.

---

### LOW-004: TOCTOU in Output File Check

**Location**: `.claude-mem/scripts/Export-ClaudeMemMemories.ps1:104-106`
**CWE**: CWE-367 (TOCTOU Race Condition)
**CVSS**: 2.2 (Low)

**Description**: Output path validation occurs before file write, creating a time window.

**Code**:

```powershell
if (-not $OutputFile.StartsWith($MemoriesDir)) {
    Write-Warning "Output file should be in .claude-mem/memories/ for version control"
}
```

**Attack Vector**: Attacker could race to replace directory between check and write. Extremely low probability in single-user CLI context.

**Remediation**: Use atomic write with temp file and rename:

```powershell
$TempFile = [System.IO.Path]::GetTempFileName()
# Write to temp
Move-Item $TempFile $OutputFile -Force
```

---

## Security Controls Assessment

### [PASS] Automatic Security Review Gate

The export scripts automatically invoke `Review-MemoryExportSecurity.ps1` with blocking exit code:

```powershell
# Export-ClaudeMemDirect.ps1:159-164
& $SecurityScript -ExportFile $OutputPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Security review FAILED. Violations must be fixed before commit."
    exit 1
}
```

**Effectiveness**: Prevents accidental secret commits. Manual bypass requires deleting the script call.

### [PASS] Forgetful Localhost Binding

Per ADR-037, Forgetful MCP binds to `127.0.0.1:8020` only. No network exposure.

### [PASS] SHA-256 Content Hashing

ADR-037 uses full SHA-256 for deduplication. Cryptographically secure, no truncation.

### [PASS] Input Validation in ADR-037 Router

The Memory Router (planned implementation) includes input validation:

```powershell
[ValidatePattern('^[a-zA-Z0-9\s\-.,_()&:]+$')]
[ValidateLength(1, 500)]
[string]$Query
```

### [WARNING] Exit Code Checking Not Universal

Some scripts capture external tool output without checking `$LASTEXITCODE`:

| Script | Line | Issue |
|--------|------|-------|
| Import-ClaudeMemMemories.ps1 | 57 | `npx tsx ... 2>&1 | Out-Null` hides errors |

**Recommendation**: Always check exit codes:

```powershell
npx tsx $PluginScript $File.FullName
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Import failed for $($File.Name)"
}
```

---

## Threat Model Summary

### Attack Surface

| Surface | Risk | Mitigations |
|---------|------|-------------|
| SQLite database | Medium | Local-only, file permissions |
| npx subprocess calls | Medium | Argument validation recommended |
| Forgetful MCP | Low | Localhost-only, no remote access |
| Exported JSON files | Low | Automatic secret scanning |
| Git commits | Low | Pre-commit security review |

### Threat Actors

| Actor | Capability | Likelihood |
|-------|------------|------------|
| Malicious collaborator | High | Low (trusted team assumed) |
| Compromised dependency | Medium | Low (npx tsx chain) |
| Accidental secret leak | N/A | Medium (human error) |

### Data Flow Security

```text
Session Observations -> SQLite DB -> Export Script -> JSON File -> Security Scan -> Git
                                                           ^
                                                           |
                                                    [BLOCKING GATE]
```

---

## Recommendations

### Required Before Merge (Conditions)

1. **Add SQL injection protection** to Export-ClaudeMemDirect.ps1 (MEDIUM-001)
   - Validate `$Project` parameter with `[ValidatePattern('^[a-zA-Z0-9_-]+$')]`

2. **Add Query parameter validation** to Export-ClaudeMemMemories.ps1 (MEDIUM-002)
   - Validate `$Query` parameter with `[ValidatePattern('^[a-zA-Z0-9\s\-_.,()]*$')]`
   - Allow empty string for "export all"

3. **Add missing secret patterns** to Review-MemoryExportSecurity.ps1 (MEDIUM-003)
   - Add AWS, Azure, Slack, npm token patterns

### Recommended (Non-Blocking)

4. Add symlink check to Import-ClaudeMemMemories.ps1 (LOW-001)
5. Add exit code verification to Import script (per WARNING)
6. Document ultrathink security considerations (LOW-003)
7. Consider atomic file writes for exports (LOW-004)

---

## Verdict

**APPROVED_WITH_CONDITIONS**

The PR may merge after addressing the three MEDIUM severity issues:

1. SQL injection validation (MEDIUM-001)
2. Command argument validation (MEDIUM-002)
3. Secret pattern completeness (MEDIUM-003)

The overall design is sound with defense-in-depth controls. The automatic security review gate is effective. Forgetful localhost-only binding limits network exposure.

---

## Appendix: Files Reviewed

| File | Lines | Security-Relevant |
|------|-------|-------------------|
| `.claude-mem/scripts/Export-ClaudeMemMemories.ps1` | 133 | Yes |
| `.claude-mem/scripts/Import-ClaudeMemMemories.ps1` | 68 | Yes |
| `.claude-mem/scripts/Export-ClaudeMemDirect.ps1` | 194 | Yes (SQL) |
| `.claude-mem/scripts/Export-ClaudeMemFullBackup.ps1` | 108 | Yes |
| `scripts/Review-MemoryExportSecurity.ps1` | 146 | Yes (scanner) |
| `.claude/skills/research-and-incorporate/SKILL.md` | 169 | Low |
| `.claude/skills/memory-documentary/SKILL.md` | N/A | Low |
| `.claude/commands/memory-documentary.md` | 53 | Low |
| `.claude/commands/forgetful/memory-search.md` | 62 | Low |
| `.claude/commands/forgetful/memory-save.md` | 127 | Low |
| `.agents/architecture/ADR-037-memory-router-architecture.md` | 451 | Yes (design) |
| `.agents/governance/MEMORY-MANAGEMENT.md` | 489 | Documentation |
| `.agents/security/ADR-037-synchronization-security-review.md` | 200+ | Prior review |

---

## Signature

**Security Agent**: Reviewed 2026-01-03
**Risk Score**: 4/10 (Low-Medium)
**Verdict**: APPROVED_WITH_CONDITIONS
