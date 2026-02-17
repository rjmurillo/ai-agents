# Security Report: ADR-047 Plugin Mode Hook Behavior

**Scope**: ADR-047 Environment Variable Usage and Path Resolution
**Date**: 2026-02-16
**Security Agent**: Claude Opus 4.6
**Risk Level**: MEDIUM (mitigations required)

## Summary

| Finding Type | Count |
|--------------|-------|
| High | 2 |
| Medium | 2 |
| Low | 1 |

**Verdict**: **CONCERNS** - Security gaps should be documented in ADR Consequences section before acceptance.

## Executive Summary

ADR-047 establishes plugin-mode path resolution using `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECT_DIR` environment variables. The decision itself is sound (run hooks in plugin mode, use environment variables for path resolution). However, the ADR does not address the security implications of trusting these environment variables. This creates a documentation gap: implementers are not warned about the attack surface introduced by environment-controlled paths.

The **actual implementation** (e.g., `invoke_skill_learning.py`) has strong defense-in-depth protections for path traversal and code injection. The **ADR documentation** lacks guidance on these protections, creating a risk that future implementations will not apply the same rigor.

## Findings

### HIGH-001: Missing Trust Boundary Documentation for CLAUDE_PLUGIN_ROOT

**Location**: ADR-047, lines 40-46 (Path Resolution section)
**CWE**: [CWE-426: Untrusted Search Path](https://cwe.mitre.org/data/definitions/426.html)

**Description**: The ADR documents the pattern `sys.path.insert(0, _lib_dir)` where `_lib_dir` is derived from `CLAUDE_PLUGIN_ROOT` without discussing trust boundaries. An attacker who controls `CLAUDE_PLUGIN_ROOT` can inject arbitrary Python code by placing a malicious `hook_utilities.py` in the controlled directory.

**Attack Scenario**:
Attacker sets `CLAUDE_PLUGIN_ROOT` to a controlled directory, creates a malicious `lib/hook_utilities.py` that executes arbitrary code when imported. Hook executes with `sys.path[0]` pointing to attacker directory, imports attacker code.

**Impact**: Remote code execution (RCE) in hook context with user's privileges. Risk Score: 8/10 (High).

**Current State**: The ADR does not document who sets `CLAUDE_PLUGIN_ROOT`, whether it is validated, or what trust assumptions are made.

**Evidence from Implementation**:
File: `.claude/hooks/PreToolUse/invoke_skill_first_guard.py:26-32`

```python
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
```

No validation of `_plugin_root` contents or origin.

**Remediation**:
1. Add "Security Considerations" subsection to ADR Consequences
2. Document trust model: Who sets `CLAUDE_PLUGIN_ROOT`? (Claude Code runtime, not user)
3. State validation assumptions: Is the variable signed/verified by Claude Code?
4. Add guidance: "Implementations MUST NOT trust user-controlled environment variables for code loading"
5. Reference existing security pattern from `invoke_skill_learning.py` (`SAFE_BASE_DIR`, `_validate_path_string()`)

**References**:
- [OWASP: Untrusted Search Path](https://owasp.org/www-community/vulnerabilities/Untrusted_Search_Path)
- [MITRE CWE-426](https://cwe.mitre.org/data/definitions/426.html)

---

### HIGH-002: Missing Path Traversal Guidance for CLAUDE_PROJECT_DIR

**Location**: ADR-047, lines 54-56 (Project Directory Resolution)
**CWE**: [CWE-22: Improper Limitation of a Pathname to a Restricted Directory](https://cwe.mitre.org/data/definitions/22.html)

**Description**: The ADR states "All hooks use `CLAUDE_PROJECT_DIR` (via `get_project_directory()`) for consumer project paths" but does not specify path traversal defenses. Naive implementations may trust `CLAUDE_PROJECT_DIR` without validation, allowing directory escape.

**Attack Scenario**:
Attacker sets `CLAUDE_PROJECT_DIR=/tmp/safe_dir/../../../etc`. Vulnerable hook uses this directly for file operations, resolving to `/etc`, allowing arbitrary file read/write outside project boundary.

**Impact**: Arbitrary file read/write outside project boundary. Escalation to privilege escalation if system files are targeted. Risk Score: 8/10 (High).

**Current State**: The ADR does not mandate path normalization or containment checks.

**Evidence from Implementation**:
File: `.claude/hooks/Stop/invoke_skill_learning.py:194-243`

The **actual implementation** has strong protections:

```python
SAFE_BASE_DIR = Path(__file__).resolve().parents[3]

def _validate_path_string(path_str: str) -> str | None:
    """Validate BEFORE Path() construction to prevent tainted data flow."""
    # Rejects null bytes (CWE-158), control chars, obvious traversal patterns
    if "\x00" in path_str or any(char in path_str for char in ["\n", "\r", "\t"]):
        return None
    normalized = path_str.replace("\\", "/")
    if "/../" in normalized or normalized.startswith("../"):
        return None
    return path_str

def get_project_directory(hook_input: dict) -> str:
    """Defense-in-depth path validation (lines 216-243)."""
    validated_dir = _validate_path_string(raw_dir)  # PRE-VALIDATION
    candidate = (base_path / user_path).resolve(strict=False)  # NORMALIZE
    if not _is_relative_to(candidate, SAFE_BASE_DIR):  # POST-VALIDATION
        return str(SAFE_BASE_DIR)  # FALLBACK
```

This pattern is **NOT documented in the ADR**. Future implementers may not know to apply these defenses.

**Remediation**:
1. Add "Path Traversal Defense" requirement to Implementation Notes (line 99)
2. Mandate: "All implementations of `get_project_directory()` MUST normalize paths with `Path.resolve()` and validate containment before use"
3. Reference canonical implementation: `.claude/lib/hook_utilities/utilities.py:18-45`
4. Add test requirement: "Verify path traversal rejection with `../../etc/passwd` test case"
5. Document fallback behavior: "On validation failure, return safe default (e.g., repository root)"

**References**:
- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- `.gemini/styleguide.md:28-38` (existing path traversal guidance for PowerShell, should extend to Python)

---

### MEDIUM-003: os.makedirs(exist_ok=True) Directory Creation Outside Project Scope

**Location**: ADR-047, lines 57-59 (Directory Creation)
**CWE**: [CWE-73: External Control of File Name or Path](https://cwe.mitre.org/data/definitions/73.html)

**Description**: The ADR states "When a required directory (e.g., `.agents/`, `.agents/sessions/`) does not exist, create it with `os.makedirs(path, exist_ok=True)`." If `path` is derived from unvalidated `CLAUDE_PROJECT_DIR`, this could create directories outside the project scope.

**Attack Scenario**:
Attacker sets `CLAUDE_PROJECT_DIR=/var/www/html`. Hook creates `.agents/` in web server root via `os.makedirs("/var/www/html/.agents", exist_ok=True)`. Attacker can now place files in web-accessible directory.

**Impact**: Directory creation pollution, potential information disclosure if web-accessible. Risk Score: 5/10 (Medium).

**Current State**: ADR does not specify path validation before `os.makedirs()`.

**Evidence from Implementation**:
File: `.claude/skills/session-init/scripts/new_session_log_json.py:80-81`

```python
sessions_dir = os.path.join(repo_root, ".agents", "sessions")
os.makedirs(sessions_dir, exist_ok=True)
```

`repo_root` is obtained from `get_project_directory()`, which (in the canonical implementation) validates paths. However, ADR-047 does not mandate this validation.

**Remediation**:
1. Update line 59: "create it with `os.makedirs(path, exist_ok=True)` **AFTER validating path is within project boundary**"
2. Add requirement: "Directory paths MUST be constructed using `os.path.join(validated_project_dir, relative_subdir)`, never concatenated from user input"
3. Add test: "Verify directory creation rejects paths outside project root"

**References**:
- [CWE-73: External Control of File Name or Path](https://cwe.mitre.org/data/definitions/73.html)

---

### MEDIUM-004: Test Coverage Does Not Verify Security Properties

**Location**: ADR-047, lines 105-113 (Test Coverage)
**CWE**: [CWE-754: Improper Check for Unusual or Exceptional Conditions](https://cwe.mitre.org/data/definitions/754.html)

**Description**: The proposed test (`test_plugin_path_resolution_pattern()`) only verifies the **presence** of `CLAUDE_PLUGIN_ROOT` in code, not the **security** of its usage. It does not test for path traversal defense, trust boundary violations, or malicious path injection.

**Current Test** (lines 106-113):

```python
def test_plugin_path_resolution_pattern():
    """Verify all hooks with lib imports use the standard resolution pattern."""
    for hook_path in glob(".claude/hooks/**/*.py"):
        content = hook_path.read_text()
        if "from hook_utilities" in content or "from github_core" in content:
            assert 'os.environ.get("CLAUDE_PLUGIN_ROOT")' in content
            assert "sys.exit(0)" not in content  # No early exits
```

This test would **pass** for the vulnerable code in HIGH-001 (no validation of `_plugin_root`).

**Impact**: False sense of security. Regressions in path validation could pass tests. Risk Score: 6/10 (Medium).

**Remediation**:
Add security-focused test cases to Implementation Notes:

```python
def test_plugin_root_path_traversal_rejection():
    """Verify CLAUDE_PLUGIN_ROOT with traversal sequences is rejected."""
    os.environ["CLAUDE_PLUGIN_ROOT"] = "/safe/dir/../../etc"
    # Test that hook either:
    # 1. Falls back to default lib directory, OR
    # 2. Validates and rejects the traversal path

def test_project_dir_normalization():
    """Verify CLAUDE_PROJECT_DIR paths are normalized before use."""
    os.environ["CLAUDE_PROJECT_DIR"] = "/tmp/project/../../../etc"
    from hook_utilities import get_project_directory
    project_dir = get_project_directory()
    # MUST NOT resolve to /etc
    assert not project_dir.startswith("/etc")
```

Update line 105 to reference security test requirements. Add to Checklist (line 117): "Test with malicious environment variables (`../../../etc/passwd`)"

**References**:
- [OWASP Testing Guide: Path Traversal](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/01-Testing_Directory_Traversal_File_Include)
- `.claude/hooks/Stop/invoke_skill_learning.py:66-95` (example of pre-validation testing)

---

### LOW-005: No Guidance on Environment Variable Injection Attacks

**Location**: ADR-047, general (no section addresses environment variable security)
**CWE**: [CWE-16: Configuration](https://cwe.mitre.org/data/definitions/16.html)

**Description**: The ADR does not discuss who can set `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECT_DIR`, or whether hooks should validate their authenticity. In multi-user environments or CI/CD pipelines, environment variables may be attacker-controlled.

**Threat Model Gap**:
- **Assumption**: Environment variables are set by trusted Claude Code runtime
- **Reality**: In GitHub Actions, environment variables can be set by workflow authors (untrusted in forked PRs)
- **Risk**: If hooks run in untrusted contexts (e.g., `pull_request_target`), environment variables are attacker-controlled

**Impact**: Depends on deployment context. In trusted environments (developer workstation), low risk. In CI/CD with untrusted contributors, escalates to HIGH. Risk Score: 3/10 (Low, context-dependent).

**Remediation**:
1. Add "Deployment Contexts" section to ADR
2. Document trust assumptions: "These environment variables are set by Claude Code and should not be user-controllable"
3. Add warning: "If deploying hooks in CI/CD, ensure environment variables cannot be overridden by untrusted actors"
4. Reference `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` for CI/CD security requirements

**References**:
- [GitHub Security: Securing GitHub Actions](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-secrets)
- [CWE-16: Configuration](https://cwe.mitre.org/data/definitions/16.html)

---

## Threat Model

### Assets
| Asset | Value | Description |
|-------|-------|-------------|
| Consumer project files | High | User's source code, credentials, configuration |
| System files | Critical | `/etc/passwd`, `~/.ssh/id_rsa`, system configuration |
| Hook execution context | High | Runs with user's privileges, can execute arbitrary code |

### Threat Actors
| Actor | Capability | Motivation |
|-------|------------|------------|
| Malicious plugin author | High (can craft CLAUDE_PLUGIN_ROOT) | Supply chain attack, credential theft |
| Compromised environment | Medium (can set env vars) | Lateral movement, privilege escalation |
| Malicious PR contributor | Low (limited to CI context) | Code injection via workflow manipulation |

### Attack Vectors (STRIDE)

| Threat | Category | Impact | Likelihood | Mitigation Status |
|--------|----------|--------|------------|-------------------|
| Code injection via `CLAUDE_PLUGIN_ROOT` | Tampering | High | Medium | **Missing** in ADR (exists in some implementations) |
| Path traversal via `CLAUDE_PROJECT_DIR` | Information Disclosure | High | Medium | **Missing** in ADR (exists in `invoke_skill_learning.py`) |
| Directory pollution via `os.makedirs()` | Denial of Service | Medium | Low | **Missing** in ADR |
| Environment variable spoofing | Spoofing | Medium | Low | **Missing** in ADR |

### Data Flow (Trust Boundaries)

```
[Untrusted: Environment Variables]
    ↓ (no validation in ADR)
[CLAUDE_PLUGIN_ROOT, CLAUDE_PROJECT_DIR]
    ↓ (used directly for path construction)
[sys.path.insert(), os.path.join(), os.makedirs()]
    ↓ (file system operations)
[Trusted: User's file system]
```

**Trust Boundary Violation**: The ADR does not establish a validation layer between untrusted environment variables and trusted file system operations.

---

## Recommended Controls

| Control | Priority | Type | Implementation Effort |
|---------|----------|------|----------------------|
| Document trust model for environment variables | P0 | Preventive | Low (documentation update) |
| Mandate path normalization and containment checks | P0 | Preventive | Low (document existing pattern) |
| Add security test cases (path traversal, code injection) | P1 | Detective | Medium (write tests) |
| Validate `CLAUDE_PLUGIN_ROOT` origin/signature | P1 | Preventive | High (requires Claude Code API changes) |
| Document safe `os.makedirs()` usage pattern | P2 | Preventive | Low (documentation update) |

---

## Blast Radius Assessment

| If Control Fails | Systems Affected | Data at Risk | Containment Strategy |
|------------------|------------------|--------------|---------------------|
| Code injection via `CLAUDE_PLUGIN_ROOT` | All hooks, all projects using plugin | Source code, credentials, SSH keys | **Immediate**: Claude Code should sign/verify `CLAUDE_PLUGIN_ROOT` <br> **Current**: User education, code review |
| Path traversal via `CLAUDE_PROJECT_DIR` | Hooks that create/modify files | Project files, system configuration | **Immediate**: Mandate canonical `get_project_directory()` implementation <br> **Current**: Implementation-dependent |
| Directory pollution | Consumer projects | Disk space, web server exposure | **Immediate**: Validate paths before `os.makedirs()` <br> **Current**: `exist_ok=True` prevents errors, but does not prevent pollution |

**Worst Case Impact**: Arbitrary code execution in hook context with user privileges, leading to credential theft or supply chain compromise.

**Isolation Boundaries**: Hooks run in-process with Claude Code. No process isolation. Defense relies entirely on path validation.

---

## Dependency Security

Not applicable (ADR-047 does not introduce new dependencies).

---

## Compliance Implications

- **OWASP Top 10:2021 A03 (Injection)**: Path traversal and code injection risks align with A03:2021 guidance. ADR should reference OWASP mitigation strategies.
- **OWASP Agentic Top 10:2026 ASI05 (Code Execution)**: Environment-controlled paths enabling code execution is a direct ASI05 risk vector.

---

## Recommendations

### Immediate Actions (P0)

1. **Add "Security Considerations" section to ADR-047 Consequences**:

```markdown
### Security Considerations

Environment variables `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECT_DIR` form a trust boundary.
Implementations MUST validate these values before file system operations:

- **Path Normalization**: Use `Path.resolve()` to eliminate `..` sequences
- **Containment Validation**: Verify resolved paths remain within expected boundaries
- **Pre-Validation**: Reject malicious patterns (null bytes, control characters) before `Path()` construction
- **Fallback**: Return safe defaults on validation failure

**Canonical Implementation**: `.claude/lib/hook_utilities/utilities.py:18-45`

**Test Requirements**: All hooks MUST pass path traversal rejection tests (e.g., `../../etc/passwd`).
```

2. **Update Implementation Notes Checklist (line 119)**:

```markdown
1. Use the standard 5-line import boilerplate if importing from `.claude/lib/`
2. Use `get_project_directory()` for consumer project paths
3. **Validate all paths are within project boundary before file operations**
4. Use `os.makedirs(path, exist_ok=True)` for required directories **AFTER path validation**
5. Never gate behavior on `CLAUDE_PLUGIN_ROOT` presence
6. Test with `CLAUDE_PLUGIN_ROOT=/tmp/test python3 hook.py` to verify plugin mode
7. **Test with malicious environment variables to verify rejection** (`CLAUDE_PROJECT_DIR=../../etc`)
```

3. **Reference Existing Security Patterns**:
Add to ADR References section:

```markdown
- `.gemini/styleguide.md:24-50` (Security Patterns for Path Traversal)
- `.claude/hooks/Stop/invoke_skill_learning.py:66-95` (`_validate_path_string` pattern)
- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` (CI/CD security requirements)
```

### Follow-Up Actions (P1)

4. **Enhance Test Coverage** (update `tests/test_plugin_path_resolution.py`):
   - Add `test_plugin_root_path_traversal_rejection()`
   - Add `test_project_dir_normalization()`
   - Add `test_directory_creation_boundary_check()`

5. **Document Trust Model**:
   - Who sets `CLAUDE_PLUGIN_ROOT`? (Claude Code runtime)
   - Is it user-modifiable? (Should not be)
   - How is authenticity verified? (Currently: not verified, opportunity for improvement)

### Strategic Actions (P2)

6. **Consider Runtime Validation**:
   - Explore Claude Code API support for signing/verifying `CLAUDE_PLUGIN_ROOT`
   - Implement hook library checksum validation at load time

---

## Verdict

**CONCERNS** - Security gaps should be documented in ADR Consequences section before acceptance.

**Rationale**: The ADR-047 decision (run hooks in plugin mode, use environment variables for paths) is architecturally sound. However, the lack of security guidance creates a documentation gap that risks insecure implementations. The **existing codebase** has strong protections (e.g., `invoke_skill_learning.py`), but the **ADR does not require these protections**, creating a risk of regression.

**Recommendation**: ACCEPT ADR-047 with REQUIRED amendments:

1. Add "Security Considerations" to Consequences section (P0, BLOCKING)
2. Mandate path validation in Implementation Notes checklist (P0, BLOCKING)
3. Reference canonical secure implementations (P0, BLOCKING)
4. Enhance test coverage with security test cases (P1, before merge)

Once these amendments are incorporated, the ADR will be **APPROVED** from a security perspective.

---

## References

- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [CWE-73: External Control of File Name or Path](https://cwe.mitre.org/data/definitions/73.html)
- [CWE-426: Untrusted Search Path](https://cwe.mitre.org/data/definitions/426.html)
- [OWASP: Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [OWASP Top 10:2021 A03 - Injection](https://owasp.org/Top10/A03_2021-Injection/)
- [OWASP Agentic Top 10:2026 ASI05 - Code Execution](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- `.gemini/styleguide.md:24-50` (Project Security Patterns)
- `.claude/hooks/Stop/invoke_skill_learning.py:66-129` (Canonical Path Validation)
- `.agents/governance/SECURITY-REVIEW-PROTOCOL.md` (Security Review Protocol)

---

*Security Report Date: 2026-02-16*
*Security Agent: Claude Opus 4.6 (security specialist)*
*Review Scope: ADR-047-plugin-mode-hook-behavior.md*
*Risk Assessment: MEDIUM (2 High, 2 Medium, 1 Low findings)*
*Recommended Action: ACCEPT with REQUIRED security amendments*
