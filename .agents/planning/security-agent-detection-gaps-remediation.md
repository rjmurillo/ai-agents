# Security Agent Detection Gaps Remediation Plan

## Overview

The security agent missed two CRITICAL vulnerabilities (CWE-22 path traversal, CWE-77 command injection) in PR #752 that were caught by Gemini Code Assist. Root cause analysis reveals systematic gaps: incomplete CWE coverage (only 3 CWEs documented), lack of PowerShell-specific security patterns (0.2% coverage despite ADR-005 PowerShell-only mandate), and no feedback loop for missed vulnerabilities.

This plan implements comprehensive CWE-699 framework integration into src/claude/security.md, expands coverage from 3 to 30+ high-priority CWEs across 11 weakness categories, adds PowerShell security checklist with concrete examples, establishes severity calibration criteria, creates feedback loop infrastructure with Forgetful memory integration, implements security benchmark suite for agent capability testing, adds second-pass review gate for critical file paths, and updates documentation. Estimated effort: 39 hours across 7 milestones.

## Planning Context

### Decision Log

| Decision | Reasoning Chain |
|----------|-----------------|
| CWE-699 comprehensive integration over minimal expansion | Root cause analysis shows systematic gap (not one-time oversight) -> minimal expansion (3 to 10 CWEs) addresses symptoms not cause -> CWE-699 provides development-oriented framework covering 11 weakness categories -> comprehensive approach prevents future detection gaps with P(success)=85% vs 40% for minimal |
| Embed CWE categories directly in security.md vs external reference | Security agent needs explicit guidance to reliably detect patterns -> external reference link relies on agent general knowledge (proven insufficient by missed vulnerabilities) -> embedded categories provide concrete detection patterns -> agent can match code against specific CWE descriptions without external lookup |
| PowerShell checklist as section within security.md vs separate file | Security agent reads single prompt file (security.md) -> separate file creates fragmentation requiring multiple reads -> context-adjacent placement (PowerShell checklist near general security guidance) provides coherent review flow -> single source of truth reduces maintenance burden |
| Dual tracking (Forgetful + GitHub Issues) for feedback loop vs Issues only | Forgetful enables semantic search ("find all false negatives related to PowerShell") -> GitHub Issues provide accountability and tracking -> dual storage maximizes discoverability (semantic) and visibility (project management) -> Issues-only loses semantic search capability proven valuable in memory-first architecture |
| Benchmark suite for agent capability testing vs automated pre-commit static analysis | Security agent is LLM-based reviewer, not static analyzer -> capability testing validates agent detection across CWE categories -> PSScriptAnalyzer (static analysis) is complementary baseline check, not replacement -> benchmark suite tests agent, PSScriptAnalyzer tests code (different layers, both needed) |
| 30 CWEs initial subset vs full 800+ from CWE-699 | CWE-699 contains 800+ weaknesses total -> agent prompt has token limits -> 30 high-priority CWEs cover OWASP Top 10 + RCA findings (CWE-22, CWE-77) -> iterative expansion prevents prompt bloat while addressing immediate gaps -> backtrack cost LOW if 30 proves insufficient (can expand incrementally) |
| CVSS-based severity calibration vs custom scoring | CVSS is industry-standard vulnerability scoring system (0.1-10.0) -> custom scoring requires maintenance and calibration overhead -> CVSS provides objective criteria with existing documentation -> threat actor context (local vs remote) applied as modifier to CVSS base score -> reuses proven framework rather than reinventing |
| Gradual CI rollout for second-pass gate vs immediate enforcement | PR #669 retrospective: 100% of wrong-branch commits from missing verification -> new CI gate could break existing workflows -> test in feature branch validates PSScriptAnalyzer integration without blocking main -> gradual rollout (feature branch -> staging -> production) reduces blast radius of CI integration failures |

### Rejected Alternatives

| Alternative | Why Rejected |
|-------------|--------------|
| Minimal expansion (3 CWEs to 10 CWEs) | P(success)=40% - addresses symptoms not root cause, systematic gap requires systematic solution, would require multiple rework cycles as new CWE classes emerge, does not prevent future embarrassment from missed vulnerability categories |
| Language-specific security agents (PowerShell, Python, etc.) | Deferred to P3 - introduces agent proliferation complexity (5+ languages = 5+ agents), increases maintenance burden (security updates must sync across agents), general agent with language-specific sections scales better initially, can refactor to specialized agents if single-agent approach proves insufficient |
| Link to external CWE-699 reference without embedding | Relies on agent general knowledge proven insufficient by PR #752 failures, agent prompt needs explicit patterns to match against, external links create dependency on agent's web access and interpretation capability, embedded content provides direct guidance |
| Separate powershell-security.md file | Creates fragmentation requiring agent to read multiple files, loses context-adjacent placement benefits (PowerShell patterns near general security principles), increases maintenance burden (two files to update for security changes), violates single source of truth principle |
| GitHub Issues only for false negative tracking | Loses semantic search capability critical for "find all PowerShell false negatives" queries, Issues are project management tool not knowledge graph, Forgetful enables pattern analysis over time ("are we missing entire CWE category?"), dual storage maximizes both discoverability and accountability |
| Automated pre-commit static analysis instead of benchmark suite | PSScriptAnalyzer is complementary not replacement - tests code not agent capability, benchmark suite validates agent detection patterns across CWE categories, need to test "does security agent catch CWE-22?" not "does code have CWE-22?", different validation layers (agent capability vs code quality) |

### Constraints & Assumptions

**Technical Constraints**:
- PowerShell-only scripting per ADR-005 (no .sh or .py files for scripts)
- Security agent prompt at src/claude/security.md currently 522 lines
- Token limit for agent prompts (estimated 50K tokens, current usage ~15K)
- Forgetful MCP server availability at localhost:8020
- PSScriptAnalyzer minimum version 1.22.0 for severity classification

**Organizational Constraints**:
- PR #752 blocked pending CRITICAL vulnerability fixes (completed)
- Issue #755 tracks security agent failure for accountability
- Monthly security review cadence from governance docs
- Session protocol requires BLOCKING gates (can enforce feedback loop compliance)

**Dependencies**:
- Forgetful MCP server for semantic memory storage (M4)
- PSScriptAnalyzer for PowerShell static analysis (M6)
- GitHub Actions for CI/CD workflows (M6)
- CWE-699 framework from MITRE (M1)
- OWASP Top 10:2021 for CWE mapping (M1)
- OWASP PowerShell Security Cheat Sheet for reference (M2)

**Default Conventions Applied**:
- domain: file-creation - Extend existing files unless separation trigger applies (>500 lines, distinct module)
- domain: documentation - CLAUDE.md uses tabular index format not prose
- domain: testing - Pester tests in Tests/ subdirectory matching source structure

### Known Risks

| Risk | Mitigation | Anchor |
|------|------------|--------|
| M1: CWE-699 too broad (800+ weaknesses total) may overwhelm agent prompt | Start with 30 high-priority CWEs covering OWASP Top 10 + RCA findings, expand iteratively based on false negative tracking | .agents/analysis/security-agent-failure-rca.md:123 "only 3 CWEs listed: CWE-78, CWE-79, CWE-89" |
| M4: Feedback loop adoption requires discipline, may be skipped | Make BLOCKING gate in SESSION-PROTOCOL.md, pre-commit validation enforces retrospective completion | .agents/SESSION-PROTOCOL.md:15-30 (existing pattern: "MUST complete ALL before any work") |
| M5: Benchmark maintenance burden as vulnerability patterns evolve | Start small (10 test cases), grow organically based on false negatives, prioritize recent RCA findings (CWE-22, CWE-77) | Accepted risk: maintenance is ongoing cost of capability validation |
| M6: CI integration breaks existing workflows, blocks legitimate PRs | Test in feature branch first, validate PSScriptAnalyzer integration on known violations, gradual rollout (feature -> staging -> production), document bypass procedure for false positives | .github/workflows/ci.yml (existing CI pattern: conditional execution, manual bypass via labels) |

## Invisible Knowledge

### Architecture

```
Security Agent Detection Pipeline:

  ┌─────────────────────────────────────────────────────────┐
  │ security.md (Expanded)                                  │
  │ - CWE-699 Categories (11) with 30+ High-Priority CWEs  │
  │ - PowerShell Security Checklist (25+ items)            │
  │ - Severity Calibration Criteria (CVSS + context)       │
  └──────────────────┬──────────────────────────────────────┘
                     │
                     v
  ┌─────────────────────────────────────────────────────────┐
  │ Security Agent Review                                   │
  │ - Reads PR changes                                      │
  │ - Matches against CWE patterns                          │
  │ - Applies PowerShell checklist                          │
  │ - Scores severity with CVSS                             │
  └──────────────────┬──────────────────────────────────────┘
                     │
                     v
  ┌─────────────────────────────────────────────────────────┐
  │ Output: Security Report (.agents/security/SR-*.md)      │
  └──────────────────┬──────────────────────────────────────┘
                     │
          ┌──────────┴────────────┐
          │                       │
          v                       v
  ┌──────────────┐       ┌──────────────────────┐
  │ Human Review │       │ Feedback Loop (M4)   │
  │ (Gemini Bot) │       │ - Compare findings   │
  │              │       │ - Extract misses     │
  └──────────────┘       │ - Store in Forgetful │
                         │ - Update benchmarks  │
                         └──────────────────────┘
```

### Data Flow

```
Code Changes (Local)
    |
    v
PRE-COMMIT HOOK (.githooks/pre-commit)
    |
    +---> PSScriptAnalyzer (M6) --> Fail on CRITICAL --> Block Commit
    |           |
    |           v PASS
    +---> Security Agent Review --> Generate SR-*.md --> Validate Report Exists --> Block if Missing
                |
                v PASS
            Commit Succeeds (with SR-*.md included)
                |
                v
            PR Created (includes SR-*.md in .agents/security/)
                |
                v
            CI/CD Validation (verify SR-*.md present, no tampering)
                |
                +---> Bot Reviewer (Gemini Code Assist) --> Reviews Code + SR-*.md
                |                                                   |
                |                                                   v
                |                                           Identifies Misses?
                |                                                   |
                |                                                   +---> YES: IMMEDIATE RCA (M4)
                |                                                   |         |
                |                                                   |         v
                |                                                   |    Update security.md Prompt
                |                                                   |         |
                |                                                   |         v
                |                                                   |    Store in Forgetful + Serena
                |                                                   |         |
                |                                                   |         v
                |                                                   |    Update Benchmarks (M5)
                |                                                   |         |
                |                                                   |         v
                |                                                   |    Block PR Merge (re-review required)
                |                                                   |
                |                                                   +---> NO: PR Approved
                v
            PR Merge Decision
```

### Why This Structure

**Shift-Left Security Architecture**: All security validation happens BEFORE PR creation in pre-commit hook. PSScriptAnalyzer catches basic violations (unquoted variables, hardcoded credentials). Security agent applies CWE-699 framework with PowerShell-specific patterns. Security report (SR-*.md) generated and committed with code changes. This prevents vulnerable code from ever reaching PR stage.

**Immediate Feedback Loop**: Bot reviewers (Gemini Code Assist) or human reviewers identifying agent misses trigger IMMEDIATE RCA and agent update (not monthly batch). False negatives flow: Bot identifies miss -> RCA execution -> security.md prompt update -> Forgetful + Serena memory storage -> benchmark suite update -> PR re-review required. This creates real-time learning cycle preventing recurrence.

**Memory Integration**: Both Forgetful (semantic search, cross-project patterns) and Serena (project-specific context, code symbols) store security findings. Dual storage enables: (1) semantic search for "all CWE-22 false negatives", (2) project-specific pattern tracking, (3) cross-session continuity for agent improvements.

**Module Boundaries**:
- `src/claude/security.md` - Agent prompt and detection patterns (knowledge base)
- `scripts/security/` - Automation scripts for retrospective and pre-commit checks
- `.agents/governance/` - Severity criteria and review protocols (policies)
- `.agents/security/benchmarks/` - Capability testing (validation)
- `.github/workflows/` - CI integration (enforcement)

Reorganizing would break separation between knowledge (prompts), automation (scripts), policy (governance), validation (benchmarks), and enforcement (CI).

### Invariants

**CWE Coverage Completeness**: At minimum, all CWEs from OWASP Top 10:2021 must be represented. Removing a CWE requires justification in Decision Log.

**PowerShell Pattern Accuracy**: All UNSAFE/SAFE example pairs must be validated with actual vulnerable code. No hypothetical examples.

**Severity Calibration Consistency**: CVSS base score + threat actor modifier must produce deterministic severity classification. Two reviewers given same vulnerability must arrive at same severity.

**Feedback Loop Execution**: Every external security review (Gemini, manual pentesting) must trigger retrospective. Skipping retrospective requires documented waiver in session log.

**Benchmark Validity**: Every benchmark test case must be based on real-world vulnerability (no synthetic examples). Each test case must have expected finding documented.

### Tradeoffs

**Comprehensive vs Minimal CWE Coverage**:
- Cost: Larger agent prompt (30+ CWEs vs 3), potential token overhead, longer review time
- Benefit: Systematic coverage prevents future detection gaps, addresses root cause not symptoms
- Choice: Comprehensive - P(success)=85% vs 40% for minimal, root cause demands systematic fix

**Embedded vs External CWE Reference**:
- Cost: Maintenance burden (CWE updates require manual prompt edits), prompt size increase
- Benefit: Reliable detection (no dependency on agent external knowledge), explicit pattern matching
- Choice: Embedded - proven external reference insufficient (PR #752 evidence)

**Dual Tracking (Forgetful + Issues) vs Single Source**:
- Cost: Dual write overhead, potential inconsistency between systems
- Benefit: Semantic search (Forgetful) + project visibility (Issues), maximizes discoverability
- Choice: Dual - memory-first architecture (ADR-007) prioritizes semantic search, Issues provide accountability

**Gradual vs Immediate CI Rollout**:
- Cost: Delayed enforcement (vulnerabilities could merge during rollout), implementation complexity
- Benefit: Reduced blast radius (CI integration failures don't block all PRs), validation in feature branch
- Choice: Gradual - PR #669 retrospective shows verification failures have high impact, risk mitigation justified

## Milestones

### Milestone 1: CWE Coverage Expansion

**Files**:
- `src/claude/security.md` (MODIFY, lines 50-60)

**Flags**: needs TW rationale

**CWE Skill Consideration**:

Given the complexity of analyzing 30+ CWEs with specific PowerShell patterns, CWE analysis may warrant implementation as a separate skill invoked by the security agent during workflow. This would enable: (1) Modular CWE detection (skill updated independently), (2) Focused prompts (CWE-specific analysis without bloating main security.md), (3) Parallel invocation (multiple CWE checks simultaneously), (4) Reusability across agents (other agents can invoke CWE skill).

**Decision**: Start with integrated approach (CWE list in security.md per this milestone). If prompt size exceeds 50K tokens or detection quality degrades, extract to separate `/cwe-analyzer` skill. Monitor token usage during M1 implementation.

**Requirements**:
- Replace 3-CWE list (CWE-78, CWE-79, CWE-89) with 11 CWE-699 categories
- Add 30 high-priority CWEs covering: Injection (22, 77, 78, 89, 91, 94), Path Traversal (22, 23), Authentication (287, 798, 640), Authorization (285, 863), Cryptography (327, 759), Input Validation (20, 129), Resource Management (400, 770), Error Handling (209, 532), API Abuse (306, 862), Race Conditions (362, 367), Code Quality (484, 665)
- Cross-reference each CWE with OWASP Top 10:2021 mapping where applicable
- Provide 1-sentence description per CWE explaining vulnerability class
- Organize by CWE-699 category with category labels (e.g., "[Injection]", "[Authentication]")

**Acceptance Criteria**:
- Security agent prompt contains 30+ CWEs (currently 3)
- Each CWE has category label from CWE-699 taxonomy
- At least 8 of 11 CWE-699 categories represented
- All OWASP Top 10:2021 items mapped to specific CWEs
- Markdown linting passes (npx markdownlint-cli2)
- CWE-22 and CWE-77 (from PR #752 failures) explicitly listed

**Code Changes**:

```diff
--- src/claude/security.md
+++ src/claude/security.md
@@ -52,7 +52,95 @@ When reviewing code for security vulnerabilities:
   - Design review principles (least privilege, defense in depth, fail secure)
   - Attack surface analysis (entry points, trust boundaries, data flow)
   - Threat modeling (STRIDE: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege)
-  - CWE detection (CWE-78 shell injection, CWE-79 XSS, CWE-89 SQL injection)
+  - CWE detection (CWE-699 Software Development View):
+
+    **[Injection and Code Execution]**
+    - CWE-22: Path Traversal - Improper limitation of pathname to restricted directory (OWASP A01:2021 Broken Access Control)
+    - CWE-77: Command Injection - Improper neutralization of special elements used in a command
+    - CWE-78: OS Command Injection - Improper neutralization of special elements used in an OS command (OWASP A03:2021 Injection)
+    - CWE-89: SQL Injection - Improper neutralization of special elements used in an SQL command (OWASP A03:2021 Injection)
+    - CWE-91: XML Injection - Improper neutralization of special elements used in an XML document
+    - CWE-94: Code Injection - Improper control of generation of code (OWASP A03:2021 Injection)
+
+    **[Authentication and Session Management]**
+    - CWE-287: Improper Authentication - Failure to properly verify identity (OWASP A07:2021 Identification and Authentication Failures)
+    - CWE-798: Use of Hard-coded Credentials - Credentials embedded in code or configuration
+    - CWE-640: Weak Password Recovery Mechanism - Password reset without proper identity verification
+
+    **[Authorization and Access Control]**
+    - CWE-285: Improper Authorization - Failure to restrict operations to authorized users (OWASP A01:2021 Broken Access Control)
+    - CWE-863: Incorrect Authorization - Authorization check missing or incorrect logic
+
+    **[Cryptography]**
+    - CWE-327: Use of Broken or Risky Cryptographic Algorithm - Weak encryption, hashing, or signing (OWASP A02:2021 Cryptographic Failures)
+    - CWE-759: Use of One-Way Hash without Salt - Password hashing without salt enables rainbow table attacks
+
+    **[Input Validation and Representation]**
+    - CWE-20: Improper Input Validation - Failure to validate or incorrectly validate input
+    - CWE-129: Improper Validation of Array Index - Out-of-bounds read/write via untrusted index
+
+    **[Resource Management]**
+    - CWE-400: Uncontrolled Resource Consumption - Missing limits on memory, CPU, disk, or network usage (OWASP A04:2021 Insecure Design)
+    - CWE-770: Allocation of Resources Without Limits or Throttling - No rate limiting or resource quotas
+
+    **[Error Handling and Logging]**
+    - CWE-209: Generation of Error Message Containing Sensitive Information - Stack traces or internal details in error responses (OWASP A04:2021 Insecure Design)
+    - CWE-532: Insertion of Sensitive Information into Log File - Passwords, tokens, or PII in logs
+
+    **[API and Function Abuse]**
+    - CWE-306: Missing Authentication for Critical Function - API endpoints accessible without credentials
+    - CWE-862: Missing Authorization - Authenticated but not authorized to perform operation
+
+    **[Race Conditions and Concurrency]**
+    - CWE-362: Concurrent Execution using Shared Resource with Improper Synchronization (Race Condition)
+    - CWE-367: Time-of-check Time-of-use (TOCTOU) Race Condition - Security check invalidated before use
+
+    **[Code Quality and Maintainability]**
+    - CWE-484: Omitted Break Statement in Switch - Unintended fallthrough logic
+    - CWE-665: Improper Initialization - Variables used before assignment or default values insecure
+
   - OWASP Top 10 (2021):
     1. Broken Access Control
     2. Cryptographic Failures
```

### Milestone 2: PowerShell Security Checklist

**Files**:
- `src/claude/security.md` (APPEND new section after line 200)

**Flags**: needs TW rationale, needs conformance check

**Technical Writer Guidance** (add these WHY comments to code examples):

**Command Injection WHY**: PowerShell passes unquoted arguments directly to shell → Shell interprets metacharacters (;|&><) as command separators, not literals → Attack: `$Query = "; rm -rf /"` executes TWO commands → Solution: Quotes force literal string interpretation, metacharacters become data not operators

**Path Traversal WHY**: StartsWith() performs string comparison on raw input → ".." sequences resolve AFTER comparison → "..\..\etc\passwd" passes StartsWith check → File system THEN resolves ".." to parent directory → Solution: GetFullPath() resolves ".." sequences BEFORE comparison, validates resolved path

**Code Execution WHY**: Invoke-Expression treats string as PowerShell code → No input sanitization or command whitelisting → User input passed directly to interpreter → Solution: Hashtable restricts to predefined commands, user selects KEY not syntax, script block execution isolates input from interpreter

**Requirements**:
- Add "PowerShell Security Checklist" section with 6 subsections: Input Validation, Command Injection Prevention, Path Traversal Prevention, Secrets and Credentials, Error Handling, Code Execution
- Each subsection has 3-5 checklist items (total 25+ items)
- Provide side-by-side UNSAFE vs SAFE code examples for top 3 patterns:
  1. Quoting variables in external commands (CWE-77)
  2. GetFullPath() for path normalization (CWE-22)
  3. Invoke-Expression risks (CWE-94)
- Reference OWASP PowerShell Security Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/PowerShell_Security_Cheat_Sheet.html)
- Examples based on PR #752 vulnerabilities (Export-ClaudeMemMemories.ps1)

**Acceptance Criteria**:
- New section exists at src/claude/security.md:~200-350
- Contains 25+ checklist items total (verified by checklist count)
- Includes 3 side-by-side UNSAFE/SAFE example pairs
- External reference link to OWASP present and valid
- Markdown linting passes (npx markdownlint-cli2)
- Examples match actual code from .claude-mem/scripts/ (not hypothetical)

**Code Changes**:

```diff
--- src/claude/security.md
+++ src/claude/security.md
@@ -200,6 +200,152 @@ When reviewing code for security vulnerabilities:
 ## Security Testing Approach

 ### Static Analysis
+
+## PowerShell Security Checklist
+
+When reviewing PowerShell scripts (.ps1, .psm1), verify:
+
+### Input Validation
+
+- [ ] All parameters have `[ValidatePattern]`, `[ValidateSet]`, or `[ValidateScript]` attributes
+- [ ] User input never passed directly to `Invoke-Expression` or `iex`
+- [ ] File paths validated with `[ValidateScript({Test-Path $_ -PathType Leaf})]` or equivalent
+- [ ] Numeric inputs have `[ValidateRange]` to prevent overflow or negative values
+- [ ] String inputs have length limits via `[ValidateLength]`
+
+### Command Injection Prevention (CWE-77, CWE-78)
+
+**UNSAFE**: Unquoted variables in external commands allow shell metacharacters (`; | & > <`) to inject commands
+
+```powershell
+# VULNERABLE - Special characters in $Query or $OutputFile can inject commands
+npx tsx $PluginScript $Query $OutputFile
+
+# Example attack: $Query = "; rm -rf /"
+```
+
+**SAFE**: Quote all variables to prevent command injection
+
+```powershell
+# SECURE - Variables quoted, metacharacters treated as literals
+npx tsx "$PluginScript" "$Query" "$OutputFile"
+
+# RECOMMENDED - Use explicit array for commands with 5+ parameters (improves readability)
+# NOTE: PowerShell splatting (@Args) only works with cmdlets/functions, not external commands
+$Args = @("$PluginScript", "$Query", "$OutputFile")
+& npx tsx $Args
+```
+
+**Checklist**:
+
+- [ ] All variables in external commands are quoted (`"$Variable"` not `$Variable`)
+- [ ] Check for unquoted variables in: `npx`, `node`, `python`, `git`, `gh`, `pwsh`, `bash`
+- [ ] For commands with 5+ parameters, use array variable with quoted elements for readability
+- [ ] Avoid string concatenation for commands: `& "cmd $UserInput"` is UNSAFE
+
+### Path Traversal Prevention (CWE-22)
+
+**UNSAFE**: `StartsWith()` without path normalization allows directory traversal via `..` sequences
+
+```powershell
+# VULNERABLE - StartsWith does not normalize paths
+$OutputFile = "..\..\..\etc\passwd"  # Escapes $MemoriesDir
+if (-not $OutputFile.StartsWith($MemoriesDir)) {
+    Write-Warning "Output file should be in $MemoriesDir"
+}
+# WARNING ONLY - Path traversal succeeds
+```
+
+**SAFE**: Use `GetFullPath()` to normalize paths before validation
+
+```powershell
+# SECURE - Paths normalized before comparison
+$NormalizedOutput = [System.IO.Path]::GetFullPath($OutputFile)
+$NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
+if (-not $NormalizedOutput.StartsWith($NormalizedDir, [System.StringComparison]::OrdinalIgnoreCase)) {
+    throw "Path traversal attempt detected. Output file must be inside '$MemoriesDir' directory."
+}
+# THROWS - Path traversal blocked
+```
+
+**Checklist**:
+
+- [ ] Use `[System.IO.Path]::GetFullPath()` to normalize paths before validation
+- [ ] Never trust `StartsWith()` for path containment checks without normalization
+- [ ] Validate resolved path is within allowed directory AFTER normalization
+- [ ] Check for symlinks with `$_.Attributes -band [IO.FileAttributes]::ReparsePoint`
+- [ ] Use `Join-Path` instead of string concatenation for path building
+
+### Secrets and Credentials
+
+- [ ] No hardcoded passwords, API keys, tokens, or connection strings
+- [ ] Use `Read-Host -AsSecureString` for password input
+- [ ] Use `ConvertTo-SecureString` and `PSCredential` for credential handling
+- [ ] Avoid `Write-Host` or logging for sensitive data (check `Write-Verbose`, `Write-Debug`)
+- [ ] Environment variables for secrets use `$env:` prefix, not hardcoded values
+
+### Error Handling
+
+- [ ] `Set-StrictMode -Version Latest` at script top to catch uninitialized variables
+- [ ] `$ErrorActionPreference = 'Stop'` for production scripts (fail-fast)
+- [ ] Try-catch blocks do not expose sensitive data in error messages
+- [ ] Exit codes checked after external commands: `if ($LASTEXITCODE -ne 0) { throw "Command failed" }`
+- [ ] Error messages do not reveal internal paths, stack traces, or implementation details
+
+### Code Execution
+
+**UNSAFE**: `Invoke-Expression` executes arbitrary code from strings
+
+```powershell
+# VULNERABLE - User input executed as PowerShell code
+$UserCommand = Read-Host "Enter command"
+Invoke-Expression $UserCommand
+
+# Example attack: $UserCommand = "Remove-Item -Recurse -Force C:\"
+```
+
+**SAFE**: Use parameterized commands or script blocks
+
+```powershell
+# SECURE - Predefined commands, user selects option
+$AllowedCommands = @{
+    'status' = { git status }
+    'log'    = { git log -n 10 }
+}
+$Choice = Read-Host "Choose: status, log"
+if ($AllowedCommands.ContainsKey($Choice)) {
+    & $AllowedCommands[$Choice]
+}
+```
+
+**Checklist**:
+
+- [ ] No use of `Invoke-Expression` unless absolutely required with sanitized input
+- [ ] No `Add-Type` with user-controlled C# code
+- [ ] No `.Invoke()` on user-provided script blocks
+- [ ] No dynamic module imports from untrusted paths
+
+### References
+
+- OWASP PowerShell Security Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/PowerShell_Security_Cheat_Sheet.html>
+- CWE-77 Command Injection: <https://cwe.mitre.org/data/definitions/77.html>
+- CWE-22 Path Traversal: <https://cwe.mitre.org/data/definitions/22.html>
+- PowerShell Security Best Practices: <https://learn.microsoft.com/en-us/powershell/scripting/dev-cross-plat/security/securing-powershell>

 ### Dynamic Testing
```

### Milestone 3: Severity Calibration

**Files**:
- `.agents/governance/SECURITY-SEVERITY-CRITERIA.md` (CREATE)

**Flags**: needs TW rationale, needs conformance check

**Requirements**:
- Document CVSS v3.1 base score thresholds: CRITICAL (9.0-10.0), HIGH (7.0-8.9), MEDIUM (4.0-6.9), LOW (0.1-3.9)
- Add threat actor context table (2x4 grid): Local CLI vs Remote Service × CRITICAL/HIGH/MEDIUM/LOW
- Provide 5 worked examples from PR #752 and RCA:
  1. CWE-22 path traversal: Base 7.5 (HIGH) + local CLI context = 9.8 (CRITICAL)
  2. CWE-77 command injection: Base 9.8 (CRITICAL) + local CLI context = 9.8 (CRITICAL)
  3. Generic SQL injection: Base 9.8 (CRITICAL) + remote service = 10.0 (CRITICAL)
  4. Missing input validation: Base 5.3 (MEDIUM) + local CLI = 5.3 (MEDIUM)
  5. Hardcoded credentials: Base 7.5 (HIGH) + remote service = 9.1 (CRITICAL)
- Include severity elevation criteria: "local exploit + privileged execution = +2.0 severity", "remote exploit + no auth required = +0.5 severity"
- Reference CVSS v3.1 Calculator: https://www.first.org/cvss/calculator/3.1

**Acceptance Criteria**:
- File exists at .agents/governance/SECURITY-SEVERITY-CRITERIA.md
- Contains CVSS scoring table with 4 severity bands
- Contains threat actor context matrix (2 actor types × 4 severity levels = 8 cells)
- Includes 5 worked examples with before/after severity calculation
- All examples cite PR #752 or security-agent-failure-rca.md for traceability
- Markdown linting passes (npx markdownlint-cli2)
- Severity elevation criteria documented (at least 2 rules)

### Milestone 4: Feedback Loop Infrastructure

**Files**:
- `scripts/security/Invoke-SecurityRetrospective.ps1` (CREATE)
- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` (CREATE, append section)

**Flags**: needs TW rationale, needs error review, needs conformance check

**Requirements**:
- Script reads security reports from `.agents/security/SR-*.md` glob pattern
- Extracts missed vulnerabilities by comparing agent findings with external review comments (GitHub API: `gh api repos/{owner}/{repo}/pulls/{pr}/comments`)
- **IMMEDIATE TRIGGER**: Bot or human reviewer identifying false negative triggers instant RCA (not monthly batch). PR remains blocked until agent updated and re-review passes.
- Stores false negatives in BOTH memory systems:
  - **Forgetful**: Semantic memory with `importance=10` (CRITICAL for agent capability), `tags=["false-negative", "security-agent", "cwe-{id}"]`, `keywords=[CWE-ID, file-path, vulnerability-class]`
  - **Serena**: Project-specific memory at `.serena/memories/security-false-negative-{cwe-id}-{pr-number}.md` with code context, RCA findings, prompt updates
- Updates `src/claude/security.md` prompt IMMEDIATELY with new pattern from false negative (blocking operation, not async)
- Updates `.agents/security/benchmarks/` with new test case from false negative vulnerability
- Updates SECURITY-REVIEW-PROTOCOL.md with immediate trigger documentation ("False negative detected -> Block PR -> Run RCA -> Update agent -> Re-review -> Merge decision")
- Error handling for Forgetful MCP unavailability: graceful degradation with warning, write to local JSON fallback (`.agents/security/false-negatives.json`)
- Error handling for Serena MCP unavailability: Fail script (BLOCKING), do not proceed with partial memory storage
- Error handling for GitHub API rate limit: Exponential backoff (1s, 2s, 4s, max 3 retries), then fail with actionable error ("Rate limit exceeded. Retry after {reset_time}.")
- Error handling for malformed SR-*.md: Validate markdown structure (YAML frontmatter, required sections), skip malformed files with warning logged to console
- Error handling for no external review: Distinguish empty findings (no vulnerabilities found) from missing review (no PR comments), log info message "No external review found for PR #{number}"
- `-WhatIf` mode: Simulate all write operations (Forgetful, JSON), output planned changes to console, exit code 0 (no actual writes)
- Script parameters: `-PRNumber` (REQUIRED), `-ExternalReviewSource` (Gemini/Manual/Other), `-WhatIf`, `-NonInteractive` (for CI invocation)

**Acceptance Criteria**:
- Script exists at scripts/security/Invoke-SecurityRetrospective.ps1
- Script runs without errors on test input (PR #752 with known false negatives)
- False negative successfully stored in BOTH memory systems:
  - Forgetful verify: `mcp__forgetful__execute_forgetful_tool("query_memory", {"query": "CWE-22 false negative", "query_context": "security retrospective"})` returns `importance=10`
  - Serena verify: `.serena/memories/security-false-negative-cwe-22-pr752.md` file exists with RCA findings
- `src/claude/security.md` updated with new PowerShell pattern from PR #752 vulnerability
- `.agents/security/benchmarks/` updated with new test case from PR #752 vulnerability
- SECURITY-REVIEW-PROTOCOL.md documents immediate trigger workflow (not monthly batch)
- PSScriptAnalyzer passes with zero warnings
- Script has `-WhatIf` support (dry-run mode)
- Forgetful unavailability handled gracefully (JSON fallback, warning, exit 0)
- Serena unavailability handled as BLOCKING (fail script, exit 1, no partial storage)

### Milestone 5: Testing Framework

**Files**:
- `.agents/security/benchmarks/cwe-22-path-traversal.ps1` (CREATE)
- `.agents/security/benchmarks/cwe-77-command-injection.ps1` (CREATE)
- `.agents/security/benchmarks/README.md` (CREATE)

**Flags**: needs TW rationale, needs conformance check

**Requirements**:
- Each benchmark file contains 3-5 vulnerable code samples in PowerShell
- Samples annotated with `# VULNERABLE: [CWE-ID] [description]` tag and expected finding comment
- README.md documents benchmark usage: "Run security agent on these files via Task(subagent_type='security', prompt='Review .agents/security/benchmarks/'), verify detection report matches expected findings"
- Start with 10 total test cases across 2 files: CWE-22 (5 cases), CWE-77 (5 cases) based on PR #752 findings
- Test cases cover: basic exploit, obfuscated exploit, false positive scenario, edge case, real-world pattern from PR #752

**Acceptance Criteria**:
- 2 benchmark files exist with 10 total test cases (5 per file)
- Each test case has vulnerability annotation (`# VULNERABLE: CWE-XX ...`)
- Each test case has expected finding comment (`# EXPECTED: CRITICAL - Path traversal via .. sequences`)
- README.md documents execution procedure (agent invocation + verification)
- Security agent run on benchmarks produces expected findings report (manually verified)
- Markdown linting passes on README.md (npx markdownlint-cli2)
- At least 1 test case per file is direct copy from PR #752 vulnerable code

### Milestone 6: Pre-Commit Security Gate

**Files**:
- `.githooks/pre-commit` (MODIFY, add security validation)
- `scripts/security/Invoke-PreCommitSecurityCheck.ps1` (CREATE)
- `.github/workflows/security-report-validator.yml` (CREATE, verifies SR-*.md present in PR)

**Flags**: needs TW rationale, needs error review

**Requirements**:
- **PRE-COMMIT HOOK** (shift-left architecture):
  - Hook runs BEFORE git commit succeeds, blocks commit on security failures
  - Step 1: Run PSScriptAnalyzer on staged `.ps1` and `.psm1` files via `Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error,Warning` filtered to staged files only
  - Step 2: Fail commit on any CRITICAL or HIGH PSScriptAnalyzer findings (exit code 1)
  - Step 3: Run security agent review on PowerShell files via `Task(subagent_type='security', prompt='Review staged PowerShell files')`
  - Step 4: Generate security report at `.agents/security/SR-{branch}-{timestamp}.md` with agent findings
  - Step 5: Stage security report for commit (`git add .agents/security/SR-*.md`)
  - Step 6: Validate security report exists and is non-empty before allowing commit
  - Error handling for missing PSScriptAnalyzer: Install via `Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser` at hook start, fail with actionable error if install fails
  - Error handling for analyzer crashes: Wrap `Invoke-ScriptAnalyzer` in try-catch, log exception + file path, continue with remaining files, mark hook as failed if any crashes
  - Error handling for no PowerShell files: Skip PSScriptAnalyzer step with info message, hook succeeds (no violations to check)
  - Error handling for agent unavailable during review: Post error message to console, provide fallback instructions (manual review required)
  - Error handling for bypass label without approval: Require `security-team-approved` label AND `skip-security-review` label in PR, fail CI if only skip label present
  - Pre-commit failures provide actionable error messages with file paths and violation details
- **CI VALIDATION** (verification layer):
  - CI workflow verifies SR-*.md file present in PR (detects hook bypass)
  - Fails PR if security report missing or empty
  - Posts PR comment: "Security report missing or empty. Run pre-commit hook locally: git commit --no-verify bypassed security validation."
- **BYPASS MECHANISM** (emergency use only):
  - `git commit --no-verify` bypasses hook but triggers CI failure
  - Manual bypass requires PR comment explaining rationale + security-team approval label
- Documents critical file patterns in hook script comments with rationale (`**/Auth/**`, `**/*Credential*`, etc.)

**Acceptance Criteria**:
- Pre-commit hook exists at `.githooks/pre-commit` with security validation logic
- PSScriptAnalyzer integration working on staged files only (test with `git add` + known violation)
- Security agent review generates SR-*.md report before commit
- Security report staged and committed automatically
- Commit blocked if PSScriptAnalyzer fails or SR-*.md generation fails
- CI workflow verifies SR-*.md present in PR, fails if missing
- Hook provides clear error messages (e.g., "PSScriptAnalyzer found CRITICAL violation in file.ps1:42 - unquoted variable in external command")
- Manual bypass (--no-verify) triggers CI failure with actionable PR comment
- PSScriptAnalyzer passes on hook script itself (zero warnings)

### Milestone 7: Documentation and Training

**Files**:
- `CLAUDE.md` (MODIFY, add Security Review section under ## Critical Constraints)
- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` (MODIFY, add Examples section)
- `src/claude/security.md` (MODIFY, add PowerShell examples to Code Review section line ~390)

**Flags**: (none)

**Requirements**:
- CLAUDE.md: Add "Security Review" subsection referencing SECURITY-SEVERITY-CRITERIA.md, SECURITY-REVIEW-PROTOCOL.md, and CWE-699 coverage
- CLAUDE.md: Update in tabular index format (not prose): "| Security Review | SECURITY-SEVERITY-CRITERIA.md | CVSS-based severity classification |"
- SECURITY-REVIEW-PROTOCOL.md: Add 3 worked examples from PR #752 with annotations:
  1. CWE-22 path traversal: What agent found vs what was missed, why it was missed, how checklist prevents recurrence
  2. CWE-77 command injection: Same structure
  3. False positive scenario: When agent flags non-vulnerability, how to document acceptance
- security.md: Add PowerShell examples to existing Code Review checklist (currently line ~390-401): unquoted variables, path normalization, Invoke-Expression

**Acceptance Criteria**:
- CLAUDE.md has new Security Review subsection under ## Critical Constraints
- CLAUDE.md uses tabular index format for security references (3 rows minimum)
- SECURITY-REVIEW-PROTOCOL.md has 3 annotated examples with before/after agent findings
- security.md Code Review checklist includes 3+ PowerShell-specific items (currently 0)
- All markdown linting passes (npx markdownlint-cli2 "**/*.md")
- Cross-references updated: CLAUDE.md links to SECURITY-SEVERITY-CRITERIA.md and SECURITY-REVIEW-PROTOCOL.md
- Examples cite specific PR #752 files and line numbers (e.g., "Export-ClaudeMemMemories.ps1:115")

## Milestone Dependencies

```
M1 (CWE Expansion) ──┐
                     ├──> M4 (Feedback Loop) ──> M7 (Documentation)
M2 (PowerShell)    ──┤                    ↑
                     │                    │
M3 (Severity)      ──┘                    │
                                          │
M5 (Benchmarks) ──────────────────────────┘

M6 (CI Gate) ─────────────────────────────┘
```

**Parallel Execution**:
- M1, M2, M3 can execute in parallel (independent prompt/governance updates)
- M5, M6 can execute in parallel (independent validation/enforcement)
- M4 depends on M1, M2, M3 completion (needs CWE categories and severity criteria for retrospective)
- M7 depends on M4 completion (documents feedback loop process)

**Sequential Dependencies**:
- M4 requires M1, M2, M3 (retrospective uses CWE categories, PowerShell patterns, severity criteria)
- M7 requires M4 (documents feedback loop in SECURITY-REVIEW-PROTOCOL.md)

**Estimated Timeline** (sequential path):
- Week 1: M1, M2, M3 (parallel, 15 hours total)
- Week 2: M5, M6 (parallel, 13 hours total) + M4 start (2 hours)
- Week 3: M4 completion (4 hours) + M7 (3 hours)
- Total: 37 hours over 3 weeks

## Cross-References

- **Root Cause**: [.agents/analysis/security-agent-failure-rca.md](.agents/analysis/security-agent-failure-rca.md)
- **Evidence**: PR #752, GitHub Issue #755
- **Memory**: [.serena/memories/security-agent-vulnerability-detection-gaps.md](.serena/memories/security-agent-vulnerability-detection-gaps.md)
- **Framework**: [CWE-699 Software Development View](https://cwe.mitre.org/data/definitions/699.html)
- **Vulnerable Code**: [.claude-mem/scripts/Export-ClaudeMemMemories.ps1](.claude-mem/scripts/Export-ClaudeMemMemories.ps1)
- **Security Report**: [.agents/security/SR-pr752-memory-system-foundation.md](.agents/security/SR-pr752-memory-system-foundation.md)
