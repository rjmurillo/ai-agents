# Security Agent Detection Gaps Remediation Plan - SCRUBBED

## Scrub Summary

**Review Date**: 2026-01-03
**Reviewer**: explainer agent
**Focus Areas**: Uncertainty flags (M1-M6), WHY comments in code snippets, rationale enrichment, M7 documentation completeness

---

## Uncertainty Flags Review

### M1: CWE Coverage Expansion

**Flag**: `needs TW rationale`

**Current State**: Decision Log entry #6 provides rationale (30 CWEs vs 800+), but milestone lacks inline WHY comments explaining category selection logic.

**Enrichment Needed**:

```diff
--- CURRENT
+++ ENRICHED
 **Requirements**:
 - Replace 3-CWE list (CWE-78, CWE-79, CWE-89) with 11 CWE-699 categories
 - Add 30 high-priority CWEs covering: Injection (22, 77, 78, 89, 91, 94), Path Traversal (22, 23), Authentication (287, 798, 640), Authorization (285, 863), Cryptography (327, 759), Input Validation (20, 129), Resource Management (400, 770), Error Handling (209, 532), API Abuse (306, 862), Race Conditions (362, 367), Code Quality (484, 665)
+
+**WHY 11 categories**: CWE-699 Software Development View organizes 800+ weaknesses into 11 development-focused categories. Selecting ALL 11 categories ensures comprehensive coverage without cherry-picking (risk of blind spots). Each category addresses distinct security failure mode.
+
+**WHY 30 CWEs initial**: Token limit prevents embedding full CWE-699 (800+ weaknesses). 30 high-priority CWEs selected via: (1) OWASP Top 10:2021 mapping (covers 80% of web vulnerabilities), (2) PR #752 RCA findings (CWE-22, CWE-77 explicitly missed), (3) PowerShell-specific risks (command injection CWE-77 elevated priority due to ADR-005 PowerShell-only mandate). Coverage expandable incrementally if false negatives persist.
```

**Code Snippet WHY Comments**: M1 code changes add 11 category headers but don't explain selection criteria inline.

**Recommendation**:

```diff
 +  - CWE detection (CWE-699 Software Development View):
 +
++    <!-- WHY 11 categories: CWE-699 provides development-oriented taxonomy covering distinct failure modes.
++         Each category selected to prevent blind spots from cherry-picking. -->
++
 +    **[Injection and Code Execution]**
++    <!-- WHY prioritize: OWASP A03:2021 + PR #752 missed CWE-77 command injection -->
 +    - CWE-22: Path Traversal - Improper limitation of pathname to restricted directory (OWASP A01:2021 Broken Access Control)
 +    - CWE-77: Command Injection - Improper neutralization of special elements used in a command
```

---

### M2: PowerShell Security Checklist

**Flag**: `needs TW rationale, needs conformance check`

**Current State**: Code snippets show UNSAFE/SAFE pairs but lack inline WHY comments explaining vulnerability mechanism and fix rationale.

**Enrichment Needed**:

**Command Injection Section**:

```diff
 **UNSAFE**: Unquoted variables in external commands allow shell metacharacters (`; | & > <`) to inject commands

 ```powershell
+# WHY VULNERABLE: PowerShell passes unquoted arguments directly to shell.
+# Shell interprets metacharacters (;|&><) as command separators, not literals.
+# Attack vector: $Query = "; rm -rf /" results in TWO commands: "npx tsx" then "rm -rf /"
 # VULNERABLE - Special characters in $Query or $OutputFile can inject commands
 npx tsx $PluginScript $Query $OutputFile

 # Example attack: $Query = "; rm -rf /"
 ```

 **SAFE**: Quote all variables to prevent command injection

 ```powershell
+# WHY SECURE: Double quotes ("") force literal string interpretation.
+# Metacharacters inside quotes treated as data, not operators.
+# Shell sees single argument: "npx tsx 'path' '; rm -rf /'" - no command injection.
 # SECURE - Variables quoted, metacharacters treated as literals
 npx tsx "$PluginScript" "$Query" "$OutputFile"
```

**Path Traversal Section**:

```diff
 **UNSAFE**: `StartsWith()` without path normalization allows directory traversal via `..` sequences

 ```powershell
+# WHY VULNERABLE: StartsWith() performs string comparison on raw input.
+# "..\..\" sequences resolve AFTER comparison, so "..\..\..\etc\passwd" passes check.
+# String comparison sees: "..\.." vs "C:\MemoriesDir" - no prefix match, warning only.
+# File system THEN resolves ".." to parent directory, escaping $MemoriesDir.
 # VULNERABLE - StartsWith does not normalize paths
 $OutputFile = "..\..\..\etc\passwd"  # Escapes $MemoriesDir
 if (-not $OutputFile.StartsWith($MemoriesDir)) {
     Write-Warning "Output file should be in $MemoriesDir"
 }
 # WARNING ONLY - Path traversal succeeds
 ```

 **SAFE**: Use `GetFullPath()` to normalize paths before validation

 ```powershell
+# WHY SECURE: GetFullPath() resolves ".." sequences BEFORE comparison.
+# "..\..\etc\passwd" normalizes to "C:\etc\passwd".
+# StartsWith() compares: "C:\etc\passwd" vs "C:\MemoriesDir" - no match, throws exception.
+# Validation occurs on RESOLVED path, preventing traversal.
 # SECURE - Paths normalized before comparison
 $NormalizedOutput = [System.IO.Path]::GetFullPath($OutputFile)
 $NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
 if (-not $NormalizedOutput.StartsWith($NormalizedDir, [System.StringComparison]::OrdinalIgnoreCase)) {
     throw "Path traversal attempt detected. Output file must be inside '$MemoriesDir' directory."
 }
 # THROWS - Path traversal blocked
 ```

**Code Execution Section**:

```diff
 **UNSAFE**: `Invoke-Expression` executes arbitrary code from strings

 ```powershell
+# WHY VULNERABLE: Invoke-Expression treats string as PowerShell code.
+# No input sanitization or command whitelisting.
+# User input passed directly to PowerShell interpreter.
+# Attack vector: Any valid PowerShell syntax executes with script permissions.
 # VULNERABLE - User input executed as PowerShell code
 $UserCommand = Read-Host "Enter command"
 Invoke-Expression $UserCommand

 # Example attack: $UserCommand = "Remove-Item -Recurse -Force C:\"
 ```

 **SAFE**: Use parameterized commands or script blocks

 ```powershell
+# WHY SECURE: Hashtable restricts commands to predefined set.
+# User selects KEY, not command syntax.
+# Script block execution (`&`) isolates command logic from user input.
+# No user input interpreted as PowerShell code.
 # SECURE - Predefined commands, user selects option
 $AllowedCommands = @{
     'status' = { git status }
     'log'    = { git log -n 10 }
 }
 $Choice = Read-Host "Choose: status, log"
 if ($AllowedCommands.ContainsKey($Choice)) {
     & $AllowedCommands[$Choice]
 }
 ```

**Conformance Check Status**:

| Checklist Item | Coverage (Lines) | Conformance |
|----------------|------------------|-------------|
| Input Validation (5 items) | 314-318 | ✓ Complete |
| Command Injection Prevention (4 items) | 320-350 | ✓ Complete, **needs WHY comments** |
| Path Traversal Prevention (5 items) | 352-383 | ✓ Complete, **needs WHY comments** |
| Secrets and Credentials (5 items) | 385-390 | ✓ Complete |
| Error Handling (5 items) | 392-399 | ✓ Complete |
| Code Execution (4 items) | 401-432 | ✓ Complete, **needs WHY comments** |
| References (4 links) | 434-438 | ✓ Complete |

**Total**: 28 checklist items (exceeds 25+ requirement). **Conformance**: PASS with enrichment needed for WHY comments.

---

### M3: Severity Calibration

**Flag**: `needs TW rationale, needs conformance check`

**Current State**: Requirements provide 5 worked examples, but lack inline rationale for severity elevation rules.

**Enrichment Needed**:

```diff
 **Requirements**:
 - Document CVSS v3.1 base score thresholds: CRITICAL (9.0-10.0), HIGH (7.0-8.9), MEDIUM (4.0-6.9), LOW (0.1-3.9)
 - Add threat actor context table (2x4 grid): Local CLI vs Remote Service × CRITICAL/HIGH/MEDIUM/LOW
+
+**WHY threat actor context**: CVSS base score assumes remote network-accessible vulnerability. Local CLI execution changes threat model: (1) requires local access (higher barrier), (2) but executes with user permissions (privilege escalation risk). Context modifier calibrates base score to actual deployment environment.
+
 - Provide 5 worked examples from PR #752 and RCA:
   1. CWE-22 path traversal: Base 7.5 (HIGH) + local CLI context = 9.8 (CRITICAL)
+      **WHY elevation**: Local CLI with write access to sensitive directories (`.agents/`, `.serena/`) can overwrite session logs, corrupt memory, or inject malicious content into git commits. Privilege escalation vector: attacker with local access gains code execution via tampered scripts.
   2. CWE-77 command injection: Base 9.8 (CRITICAL) + local CLI context = 9.8 (CRITICAL)
+      **WHY no elevation**: Command injection already CRITICAL (arbitrary code execution). Local context doesn't reduce severity (still full system compromise). Score remains 9.8.
```

**Conformance Check Status**:

| Requirement | Completeness |
|-------------|--------------|
| CVSS thresholds (4 bands) | ✓ Specified |
| Threat actor table (2×4 grid) | ✓ Specified |
| 5 worked examples | ✓ Listed, **needs elevation rationale** |
| Severity elevation criteria (2+ rules) | ✓ Mentioned, **needs inline justification** |
| CVSS calculator reference | ✓ Provided |

**Conformance**: PASS with enrichment needed for elevation criteria rationale.

---

### M4: Feedback Loop Infrastructure

**Flag**: `needs TW rationale, needs error review, needs conformance check`

**Current State**: Requirements specify graceful degradation for Forgetful MCP unavailability, but lack error handling rationale and edge case coverage.

**Enrichment Needed**:

```diff
 **Requirements**:
 - Script reads security reports from `.agents/security/SR-*.md` glob pattern
+  **WHY glob pattern**: Multiple PRs may have security reports. Glob enables batch retrospective (e.g., monthly review of all merged PRs). Single-PR mode via `-PRNumber` parameter when investigating specific failure.
+
 - Extracts missed vulnerabilities by comparing agent findings with external review comments (GitHub API: `gh api repos/{owner}/{repo}/pulls/{pr}/comments`)
+  **WHY GitHub API**: External reviews (Gemini, human) post as PR comments. API provides structured access to review text for parsing. Alternative (manual copy-paste) error-prone and non-automatable.
+
 - Stores false negatives in Forgetful with `importance=9`, `tags=["false-negative", "security-agent"]`, `keywords=[CWE-ID, file-path]`
+  **WHY importance=9**: False negatives represent confirmed agent failures. High importance ensures semantic search prioritizes these memories for future pattern analysis ("find all CWE-22 misses").
+
 - Error handling for Forgetful MCP unavailability: graceful degradation with warning, write to local JSON fallback (`.agents/security/false-negatives.json`)
+  **WHY graceful degradation**: Feedback loop must not block retrospective completion. Forgetful MCP unavailability (server down, network issue) is transient. JSON fallback preserves data for later import. Script returns exit code 0 (success) with warning, not exit code 1 (failure).
```

**Error Review**:

| Error Scenario | Handling | Gaps Identified |
|----------------|----------|-----------------|
| Forgetful MCP unavailable | JSON fallback + warning | ✓ Covered |
| GitHub API rate limit | **NOT SPECIFIED** | **GAP**: Script should retry with exponential backoff or fail with actionable error |
| SR-*.md file malformed | **NOT SPECIFIED** | **GAP**: Script should validate markdown structure or skip malformed files with warning |
| PR comments contain no security findings | **NOT SPECIFIED** | **GAP**: Script should distinguish "no findings" from "no external review" |
| `-WhatIf` mode with Forgetful write | **NOT SPECIFIED** | **GAP**: WhatIf should simulate Forgetful write without actual storage |

**Recommended Error Handling Expansion**:

```diff
 - Error handling for Forgetful MCP unavailability: graceful degradation with warning, write to local JSON fallback (`.agents/security/false-negatives.json`)
+- Error handling for GitHub API rate limit: Exponential backoff (1s, 2s, 4s, max 3 retries), then fail with actionable error ("Rate limit exceeded. Retry after {reset_time}.")
+- Error handling for malformed SR-*.md: Validate markdown structure (YAML frontmatter, required sections), skip malformed files with warning logged to console
+- Error handling for no external review: Distinguish empty findings (no vulnerabilities found) from missing review (no PR comments), log info message "No external review found for PR #{number}"
+- `-WhatIf` mode: Simulate all write operations (Forgetful, JSON), output planned changes to console, exit code 0 (no actual writes)
```

**Conformance Check Status**:

| Requirement | Status |
|-------------|--------|
| Reads SR-*.md glob | ✓ Specified |
| GitHub API extraction | ✓ Specified |
| Forgetful storage | ✓ Specified |
| SECURITY-REVIEW-PROTOCOL.md cadence | ✓ Specified |
| Forgetful error handling | ✓ Specified, **needs edge case expansion** |
| Script parameters (3) | ✓ Complete |

**Conformance**: PARTIAL - needs error handling expansion for API rate limit, malformed files, empty reviews, WhatIf mode.

---

### M5: Testing Framework

**Flag**: `needs TW rationale, needs conformance check`

**Current State**: Requirements specify 10 test cases but lack rationale for test case categories (basic, obfuscated, false positive, edge case, real-world).

**Enrichment Needed**:

```diff
 **Requirements**:
 - Each benchmark file contains 3-5 vulnerable code samples in PowerShell
 - Samples annotated with `# VULNERABLE: [CWE-ID] [description]` tag and expected finding comment
 - README.md documents benchmark usage: "Run security agent on these files via Task(subagent_type='security', prompt='Review .agents/security/benchmarks/'), verify detection report matches expected findings"
 - Start with 10 total test cases across 2 files: CWE-22 (5 cases), CWE-77 (5 cases) based on PR #752 findings
 - Test cases cover: basic exploit, obfuscated exploit, false positive scenario, edge case, real-world pattern from PR #752
+
+**WHY 5 test case categories**:
+  1. **Basic exploit**: Validates agent detects textbook vulnerability. Baseline capability check.
+  2. **Obfuscated exploit**: Tests agent pattern matching against variable renaming, string concatenation, or encoding. Prevents evasion via code obfuscation.
+  3. **False positive scenario**: Ensures agent distinguishes vulnerable vs secure patterns. Example: quoted variable in command (secure) vs unquoted (vulnerable). Reduces false alarm rate.
+  4. **Edge case**: Validates agent handles boundary conditions. Example: CWE-22 with normalized path that happens to match allowed directory legitimately. Prevents over-blocking.
+  5. **Real-world pattern from PR #752**: Ground truth from actual missed vulnerability. High confidence that test case represents production failure mode.
```

**Conformance Check Status**:

| Requirement | Status |
|-------------|--------|
| 10 total test cases (5 per file) | ✓ Specified |
| Vulnerability annotations | ✓ Specified |
| Expected finding comments | ✓ Specified |
| README.md execution procedure | ✓ Specified |
| 5 test case categories | ✓ Listed, **needs rationale** |
| 1+ real PR #752 case per file | ✓ Specified |

**Conformance**: PASS with enrichment needed for test case category rationale.

---

### M6: Second-Pass Review Gate

**Flag**: `needs TW rationale, needs error review`

**Current State**: Requirements specify PSScriptAnalyzer integration and critical file patterns, but lack rationale for second-pass necessity and error handling for analyzer failures.

**Enrichment Needed**:

```diff
 **Requirements**:
 - Workflow runs PSScriptAnalyzer on all `.ps1` and `.psm1` files via `Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error,Warning`
+  **WHY PSScriptAnalyzer first**: Static analyzer catches basic violations (unquoted variables, hardcoded credentials) BEFORE agent review. Reduces agent workload by filtering out low-hanging fruit. Agent focuses on complex CWE patterns (command injection logic, path traversal edge cases).
+
 - Fails build on any CRITICAL or HIGH PSScriptAnalyzer findings (exit code 1)
+  **WHY fail-fast**: CRITICAL/HIGH findings represent confirmed security issues. Blocking PR prevents vulnerable code merge while agent review pending. Reduces time-to-detection (minutes vs hours for human review).
+
 - Requires second security agent review for files matching glob patterns: `**/Auth/**`, `**/*Credential*`, `**/*.env*`, `**/*Secret*`, `**/*Password*`
+  **WHY second-pass for critical files**: Credential handling code has asymmetric risk (one leak compromises entire system). First-pass agent review may miss context-specific issues (e.g., credential logged to file vs passed to API). Second pass with fresh context reduces false negative rate.
+
 - Documents critical file patterns in workflow YAML comments with rationale
+  **WHY YAML comments**: Maintainers must understand why certain files trigger second review. Comments prevent pattern removal during refactoring. Example: "Auth/** - authentication logic has elevated privilege escalation risk".
```

**Error Review**:

| Error Scenario | Handling | Gaps Identified |
|----------------|----------|-----------------|
| PSScriptAnalyzer not installed | **NOT SPECIFIED** | **GAP**: Workflow should install PSScriptAnalyzer via `Install-Module` or fail with actionable error |
| PSScriptAnalyzer crashes on malformed .ps1 | **NOT SPECIFIED** | **GAP**: Workflow should catch analyzer exceptions, report file path, continue with other files |
| No `.ps1` or `.psm1` files in PR | **NOT SPECIFIED** | **GAP**: Workflow should skip gracefully with info message, not fail |
| Critical file pattern matched but agent unavailable | **NOT SPECIFIED** | **GAP**: Workflow should queue manual review or fail PR with clear error |
| Manual bypass label (`skip-security-review`) without approval | **NOT SPECIFIED** | **GAP**: Workflow should verify approval from codeowner/security team before bypass |

**Recommended Error Handling Expansion**:

```diff
 - Workflow runs PSScriptAnalyzer on all `.ps1` and `.psm1` files via `Invoke-ScriptAnalyzer -Path . -Recurse -Severity Error,Warning`
+- Error handling for missing PSScriptAnalyzer: Install via `Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser` at workflow start, fail with actionable error if install fails
+- Error handling for analyzer crashes: Wrap `Invoke-ScriptAnalyzer` in try-catch, log exception + file path, continue with remaining files, mark workflow as failed if any crashes
+- Error handling for no PowerShell files: Skip PSScriptAnalyzer step with info message, workflow succeeds (no violations to check)
+- Error handling for agent unavailable during second-pass: Post PR comment requesting manual review, block merge via required status check, provide fallback contact (security team)
+- Error handling for bypass label without approval: Require `security-team-approved` label AND `skip-security-review` label, fail workflow if only skip label present
```

**Conformance Check Status**:

| Requirement | Status |
|-------------|--------|
| PSScriptAnalyzer integration | ✓ Specified, **needs error handling** |
| Fail on CRITICAL/HIGH | ✓ Specified |
| Second-pass for critical files | ✓ Specified, **needs rationale** |
| YAML comments for patterns | ✓ Specified |
| Workflow triggers | ✓ Specified |
| Manual bypass via label | ✓ Specified, **needs approval logic** |

**Conformance**: PARTIAL - needs error handling expansion for analyzer installation, crashes, empty file sets, agent unavailability, unapproved bypass.

---

### M7: Documentation and Training

**Flag**: (none) - but scrub reveals incompleteness

**Current State**: Requirements specify CLAUDE.md update, SECURITY-REVIEW-PROTOCOL.md examples, and security.md PowerShell examples. However, missing explicit documentation of benchmark execution procedure, feedback loop automation, and severity calibration workflow.

**Completeness Check**:

| Documentation Requirement | Status | Gaps Identified |
|---------------------------|--------|-----------------|
| CLAUDE.md Security Review subsection | ✓ Specified | **GAP**: No mention of benchmark suite location or execution frequency |
| CLAUDE.md tabular index | ✓ Specified | **GAP**: Missing row for benchmarks (`.agents/security/benchmarks/`) |
| SECURITY-REVIEW-PROTOCOL.md examples (3) | ✓ Specified | **GAP**: Examples don't cover severity calibration workflow (how to apply CVSS + context) |
| security.md PowerShell checklist integration | ✓ Specified | ✓ Complete |
| Benchmark execution procedure | **NOT SPECIFIED** | **GAP**: README.md (M5) documents benchmark usage, but not integrated into CLAUDE.md or SECURITY-REVIEW-PROTOCOL.md |
| Feedback loop automation | **NOT SPECIFIED** | **GAP**: SECURITY-REVIEW-PROTOCOL.md mentions monthly cadence but doesn't link to Invoke-SecurityRetrospective.ps1 usage |
| Severity calibration workflow | **NOT SPECIFIED** | **GAP**: SECURITY-SEVERITY-CRITERIA.md (M3) has criteria but no step-by-step application guide |

**Recommended Documentation Expansion**:

```diff
 **Requirements**:
 - CLAUDE.md: Add "Security Review" subsection referencing SECURITY-SEVERITY-CRITERIA.md, SECURITY-REVIEW-PROTOCOL.md, and CWE-699 coverage
 - CLAUDE.md: Update in tabular index format (not prose): "| Security Review | SECURITY-SEVERITY-CRITERIA.md | CVSS-based severity classification |"
+- CLAUDE.md: Add benchmark suite row to index: "| Security Benchmarks | .agents/security/benchmarks/ | Agent capability testing (run quarterly) |"
+- CLAUDE.md: Add feedback loop row to index: "| Security Retrospective | scripts/security/Invoke-SecurityRetrospective.ps1 | Monthly false negative extraction |"
+
 - SECURITY-REVIEW-PROTOCOL.md: Add 3 worked examples from PR #752 with annotations:
   1. CWE-22 path traversal: What agent found vs what was missed, why it was missed, how checklist prevents recurrence
   2. CWE-77 command injection: Same structure
   3. False positive scenario: When agent flags non-vulnerability, how to document acceptance
+  4. **NEW**: Severity calibration example: Step-by-step CVSS scoring for CWE-22 (Base Score → Attack Vector → Attack Complexity → Privileges Required → User Interaction → Scope → Confidentiality/Integrity/Availability Impact → Context Modifier → Final Severity)
+
+- SECURITY-REVIEW-PROTOCOL.md: Add "Automation" section with 2 subsections:
+  1. **Benchmark Execution**: "Run quarterly via `Task(subagent_type='security', prompt='Review .agents/security/benchmarks/')`, compare findings against expected results, update benchmarks based on new false negatives."
+  2. **Feedback Loop**: "Run monthly via `pwsh scripts/security/Invoke-SecurityRetrospective.ps1 -ExternalReviewSource Gemini`, import false negatives to Forgetful, update security.md with new patterns."
+
 - security.md: Add PowerShell examples to existing Code Review checklist (currently line ~390-401): unquoted variables, path normalization, Invoke-Expression
```

**Conformance**: PARTIAL - M7 requirements met but missing integration of M3 (severity workflow), M4 (automation), and M5 (benchmark execution) into primary documentation.

---

## Decision Log Rationale Review

### Multi-Step Reasoning Chains (2+ steps minimum)

| Decision | Reasoning Steps | Compliance |
|----------|-----------------|------------|
| CWE-699 comprehensive integration | 4 steps: Root cause (systematic gap) → Minimal fails (symptom fix) → CWE-699 framework (systematic solution) → P(success) quantification | ✓ PASS |
| Embed CWE categories in security.md | 3 steps: Agent needs explicit guidance → External reference proven insufficient → Embedded provides direct matching | ✓ PASS |
| PowerShell checklist within security.md | 3 steps: Single-file agent → Separate file = fragmentation → Context-adjacent = coherent flow | ✓ PASS |
| Dual tracking (Forgetful + Issues) | 4 steps: Forgetful = semantic search → Issues = accountability → Dual = maximize discoverability + visibility → Issues-only loses semantic | ✓ PASS |
| Benchmark suite vs static analysis | 3 steps: LLM vs static analyzer → Capability testing validates agent → PSScriptAnalyzer = complementary baseline | ✓ PASS |
| 30 CWEs vs full 800+ | 4 steps: CWE-699 total (800+) → Token limits → 30 covers OWASP Top 10 + RCA → Iterative expansion | ✓ PASS |
| CVSS-based severity | 4 steps: CVSS = industry standard → Custom = maintenance overhead → Objective criteria → Threat context modifier | ✓ PASS |
| Gradual CI rollout | 4 steps: PR #669 verification failures → New gate could break workflows → Feature branch validates → Gradual reduces blast radius | ✓ PASS |

**All decisions meet 2+ step requirement. No gaps identified.**

---

## Non-Obvious Logic Lacking Rationale

### Issue #1: Why 11 CWE-699 categories instead of 8 minimum?

**Location**: M1 Acceptance Criteria ("At least 8 of 11 CWE-699 categories represented")

**Gap**: Decision Log #1 justifies CWE-699 comprehensive approach but doesn't explain why acceptance allows 8/11 instead of requiring 11/11.

**Query for Clarification**: Is 8/11 threshold based on token limit constraint, or is 3-category gap acceptable for MVP? If token-limited, which 3 categories are lowest priority for PowerShell CLI context (candidates: Race Conditions, API Abuse, Code Quality)?

---

### Issue #2: Why importance=9 for false negatives instead of 10?

**Location**: M4 Requirements ("Stores false negatives in Forgetful with `importance=9`")

**Gap**: Decision Log doesn't explain why 9 instead of 10 (maximum importance). Forgetful importance scale: 10 = "critical project knowledge", 9 = "high priority knowledge". False negatives are confirmed agent failures (critical for capability improvement).

**Query for Clarification**: Is importance=9 intentional (reserve 10 for broader architectural decisions), or should false negatives be importance=10 given their direct impact on security posture?

---

### Issue #3: Why 5 test case categories for benchmarks instead of 3 (basic, real-world, false positive)?

**Location**: M5 Requirements ("Test cases cover: basic exploit, obfuscated exploit, false positive scenario, edge case, real-world pattern from PR #752")

**Gap**: Decision Log doesn't justify 5-category taxonomy. Basic + real-world + false positive covers most validation needs. Obfuscated and edge case add coverage but increase maintenance burden (M5 Known Risk: "maintenance burden as vulnerability patterns evolve").

**Query for Clarification**: Are obfuscated and edge case categories essential for MVP, or can they be deferred to post-MVP expansion based on false negative patterns from feedback loop?

---

### Issue #4: Why fail on PSScriptAnalyzer CRITICAL/HIGH but not MEDIUM?

**Location**: M6 Requirements ("Fails build on any CRITICAL or HIGH PSScriptAnalyzer findings (exit code 1)")

**Gap**: Decision Log doesn't explain severity threshold. PSScriptAnalyzer MEDIUM findings (e.g., missing parameter help, inconsistent casing) may be noise, but some MEDIUM findings have security implications (e.g., Write-Host exposing sensitive data).

**Query for Clarification**: Should workflow fail on ALL PSScriptAnalyzer findings initially (validate false positive rate), then relax to CRITICAL/HIGH after baseline established? Or is MEDIUM noise level acceptable based on prior PSScriptAnalyzer experience?

---

## Plan Prose Enrichment with Planning Context

### Overview Section

**Current**: "Root cause analysis reveals systematic gaps: incomplete CWE coverage (only 3 CWEs documented), lack of PowerShell-specific security patterns (0.2% coverage despite ADR-005 PowerShell-only mandate), and no feedback loop for missed vulnerabilities."

**Enriched with Decision Log #1 rationale**:

```diff
-Root cause analysis reveals systematic gaps: incomplete CWE coverage (only 3 CWEs documented), lack of PowerShell-specific security patterns (0.2% coverage despite ADR-005 PowerShell-only mandate), and no feedback loop for missed vulnerabilities.
+Root cause analysis reveals systematic gaps, not one-time oversight (Decision Log #1): incomplete CWE coverage (only 3 CWEs documented out of 800+ in CWE-699 framework), lack of PowerShell-specific security patterns (0.2% coverage = 1 paragraph in 522-line prompt, despite ADR-005 PowerShell-only mandate making command injection CWE-77 elevated priority), and no feedback loop for missed vulnerabilities (no mechanism to capture external review findings and update agent knowledge base). Systematic gaps require systematic solution with P(success)=85% vs 40% for minimal expansion approach.
```

### Why This Structure Section

**Current**: "Layered Security Gates: PSScriptAnalyzer catches basic violations (unquoted variables, hardcoded credentials) before agent review. Security agent applies CWE-699 framework with PowerShell-specific patterns. Human review catches agent false negatives. Each layer complements rather than duplicates."

**Enriched with Decision Log #5 rationale**:

```diff
-Layered Security Gates: PSScriptAnalyzer catches basic violations (unquoted variables, hardcoded credentials) before agent review. Security agent applies CWE-699 framework with PowerShell-specific patterns. Human review catches agent false negatives. Each layer complements rather than duplicates.
+Layered Security Gates (Decision Log #5 - Benchmark suite vs static analysis): PSScriptAnalyzer (static analyzer) catches basic violations (unquoted variables, hardcoded credentials) before agent review, testing CODE quality. Security agent (LLM-based reviewer) applies CWE-699 framework with PowerShell-specific patterns, testing AGENT capability. Human review (Gemini, manual) catches agent false negatives, validating agent detection patterns. Each layer operates on different validation target (code vs agent vs meta-validation), complementing rather than duplicating. Removing any layer creates gap: no PSScriptAnalyzer = agent waste time on trivial issues, no agent = miss complex CWE patterns, no human review = no feedback loop for agent improvement.
```

---

## Summary of Flagged Issues Requiring Clarification

| # | Issue | Location | Priority | Blocking? |
|---|-------|----------|----------|-----------|
| 1 | Why 8/11 CWE-699 categories acceptable instead of 11/11? | M1 Acceptance | Medium | No - 8 meets OWASP coverage |
| 2 | Why importance=9 for false negatives instead of 10? | M4 Requirements | Low | No - semantics only |
| 3 | Why 5 test case categories instead of 3? | M5 Requirements | Medium | No - can defer obfuscated/edge |
| 4 | Why PSScriptAnalyzer threshold CRITICAL/HIGH not ALL? | M6 Requirements | High | **YES** - impacts CI noise |
| 5 | M2 code snippets missing WHY comments | M2 Code Changes | High | **YES** - readability critical |
| 6 | M4 error handling gaps (API rate limit, malformed files) | M4 Requirements | High | **YES** - production robustness |
| 7 | M6 error handling gaps (analyzer install, crashes) | M6 Requirements | High | **YES** - CI reliability |
| 8 | M7 missing integration of M3/M4/M5 automation | M7 Requirements | Medium | No - can add post-MVP |

---

## Recommended Next Steps

1. **BLOCKING**: Address Issues #5, #6, #7 before implementation (code snippet WHY comments + error handling expansion).
2. **HIGH PRIORITY**: Clarify Issue #4 (PSScriptAnalyzer threshold) to prevent CI tuning churn.
3. **MEDIUM PRIORITY**: Clarify Issues #1, #3 (category counts) for documentation accuracy.
4. **LOW PRIORITY**: Clarify Issue #2 (importance scoring) for Forgetful consistency.
5. **POST-MVP**: Expand M7 documentation to integrate automation workflows (Issue #8).

---

## Annotated Plan Changes

### M1: CWE Coverage Expansion

**Add to Code Changes section**:

```diff
+<!-- WHY 11 categories: CWE-699 Software Development View provides development-oriented taxonomy.
+     Selecting ALL 11 categories ensures comprehensive coverage without cherry-picking risk.
+     Each category addresses distinct security failure mode (injection ≠ authentication ≠ crypto). -->
+
+<!-- WHY 30 CWEs subset: Token limit prevents embedding full CWE-699 (800+ weaknesses).
+     30 high-priority CWEs selected via:
+       1. OWASP Top 10:2021 mapping (covers 80% of web vulnerabilities)
+       2. PR #752 RCA findings (CWE-22, CWE-77 explicitly missed)
+       3. PowerShell-specific risks (CWE-77 command injection elevated priority per ADR-005)
+     Coverage expandable incrementally if false negatives persist post-deployment. -->
+
     **[Injection and Code Execution]**
+    <!-- WHY prioritize: OWASP A03:2021 Injection + PR #752 missed CWE-77 command injection.
+         PowerShell CLI context makes command injection high-probability attack vector. -->
```

### M2: PowerShell Security Checklist

**Add WHY comments to all 3 UNSAFE/SAFE pairs per enrichment section above.**

### M3: Severity Calibration

**Add to Requirements**:

```diff
+**WHY threat actor context modifier**: CVSS base score assumes remote network-accessible vulnerability. Local CLI execution changes threat model:
+  - Higher barrier: Requires local access (physical or remote shell)
+  - Privilege escalation risk: Executes with user permissions (can tamper scripts, corrupt memory, inject malicious commits)
+  - Context modifier calibrates base score to actual deployment environment (local CLI vs remote service)
+
+**WHY elevation criteria**: Generic CVSS may underestimate local privilege escalation vectors. Elevation rules:
+  - "Local exploit + privileged execution = +2.0 severity" - Attacker with local access + write to `.agents/` can inject code into git commits (supply chain attack)
+  - "Remote exploit + no auth required = +0.5 severity" - Publicly accessible vulnerability has broader attack surface (entire internet vs local users)
```

### M4: Feedback Loop Infrastructure

**Add to Requirements**:

```diff
+**Error Handling Expansion**:
+- GitHub API rate limit: Exponential backoff (1s, 2s, 4s, max 3 retries), fail with actionable error ("Rate limit exceeded. Retry after {reset_time}. Consider using GitHub PAT with higher limits.")
+- Malformed SR-*.md: Validate markdown structure (YAML frontmatter, required sections), skip with warning "SR-{name}.md missing required section: [section]. Skipping."
+- No external review: Distinguish empty findings (no vulnerabilities) vs missing review (no PR comments), log "No external review found for PR #{number}. Unable to extract false negatives."
+- `-WhatIf` mode: Simulate Forgetful write, output "WHATIF: Would store memory [title] with importance 9 and tags [false-negative, security-agent]", exit 0
```

### M5: Testing Framework

**Add to Requirements**:

```diff
+**WHY 5 test case categories** (vs 3 basic categories):
+  1. **Basic exploit**: Textbook vulnerability (e.g., unquoted variable in command). Validates baseline agent capability.
+  2. **Obfuscated exploit**: Variable renaming, string concatenation, encoding (e.g., `$c="cmd";& $c`). Prevents evasion via code obfuscation. **Required**: Attackers use obfuscation in real exploits.
+  3. **False positive scenario**: Secure pattern agent might flag (e.g., quoted variable). Reduces false alarm rate. **Required**: High false positive rate undermines agent trust.
+  4. **Edge case**: Boundary conditions (e.g., normalized path legitimately matches allowed dir). Prevents over-blocking. **Recommended**: Can defer to post-MVP if bandwidth limited.
+  5. **Real-world pattern**: Direct copy from PR #752 vulnerable code. Ground truth for production failure mode. **Required**: Ensures benchmark represents actual agent failures.
```

### M6: Second-Pass Review Gate

**Add to Requirements**:

```diff
+**Error Handling Expansion**:
+- PSScriptAnalyzer installation: `Install-Module -Name PSScriptAnalyzer -Force -Scope CurrentUser` at workflow start. Fail with "PSScriptAnalyzer installation failed. Check module repository access."
+- Analyzer crashes: Wrap `Invoke-ScriptAnalyzer` in try-catch, log "PSScriptAnalyzer crashed on file {path}: {exception}. Skipping file.", mark workflow failed if any crashes.
+- No PowerShell files in PR: Skip PSScriptAnalyzer step with "No .ps1 or .psm1 files changed. Skipping static analysis.", workflow succeeds.
+- Agent unavailable for second-pass: Post PR comment "Critical file pattern detected: {path}. Second security review REQUIRED. Agent unavailable - manual review requested from @security-team.", block merge via required status check.
+- Bypass label without approval: Require `security-team-approved` label AND `skip-security-review` label. Fail with "Skip label requires security-team-approved label. Request approval from codeowner."
```

### M7: Documentation and Training

**Add to Requirements**:

```diff
+- CLAUDE.md: Add benchmark suite row: "| Security Benchmarks | .agents/security/benchmarks/ | Agent capability testing (run quarterly) |"
+- CLAUDE.md: Add feedback loop row: "| Security Retrospective | scripts/security/Invoke-SecurityRetrospective.ps1 | Monthly false negative extraction |"
+- SECURITY-REVIEW-PROTOCOL.md: Add Example 4 - Severity Calibration: "CWE-22 path traversal severity scoring: Base CVSS (AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N = 7.5 HIGH) + Local CLI context (write access to .agents/ enables code injection = +2.0) = 9.5 CRITICAL. Justification: Attacker with local access can tamper session logs, inject malicious content into git commits (supply chain attack vector)."
+- SECURITY-REVIEW-PROTOCOL.md: Add "Automation" section with 2 subsections:
+  1. Benchmark Execution: "Run quarterly: `Task(subagent_type='security', prompt='Review .agents/security/benchmarks/')`. Compare findings against expected results. Update benchmarks based on new false negatives from feedback loop."
+  2. Feedback Loop: "Run monthly: `pwsh scripts/security/Invoke-SecurityRetrospective.ps1 -ExternalReviewSource Gemini`. Import false negatives to Forgetful. Update security.md with new PowerShell patterns."
```

---

**END OF SCRUB REPORT**
