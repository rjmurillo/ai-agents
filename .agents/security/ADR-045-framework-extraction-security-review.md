# Security Review: ADR-045 Framework Extraction via Plugin Marketplace

**Review Date**: 2026-02-07
**Reviewer**: Security Agent
**ADR Status**: Proposed
**Security Verdict**: NEEDS-REVISION

---

## Executive Summary

ADR-045 proposes extracting the ai-agents framework into a separate awesome-ai repository distributed via Claude Code plugin marketplace. The security review identifies 8 high-priority findings and 3 medium-priority findings across supply chain security, path security, hook trust boundaries, and CI template safety.

**Risk Score**: 7.2/10 (HIGH)

**Critical Concerns**:

1. **Supply Chain Security**: No plugin integrity verification, authentication, or signature validation
2. **Path Traversal Risk**: Environment variables lack normalization and containment validation
3. **Hook Trust Boundary**: Plugins execute code with consumer project privileges without sandboxing
4. **CI Template Safety**: Workflow templates distributed without SHA pinning enforcement

**Recommendation**: NEEDS-REVISION with P0 and P1 findings addressed before acceptance.

---

## Threat Model

### Assets

| Asset | Value | Description |
|-------|-------|-------------|
| Consumer project code | Critical | Source code in projects consuming awesome-ai |
| Consumer secrets | Critical | Environment variables, credentials, API tokens |
| Plugin distribution chain | High | GitHub repos, marketplace catalog |
| Hook execution environment | High | PowerShell/Python runtime with file system access |
| CI/CD pipelines | High | GitHub Actions workflows consuming templates |

### Threat Actors

| Actor | Capability | Motivation |
|-------|------------|------------|
| Malicious plugin author | High (can publish to GitHub) | Data theft, supply chain compromise |
| Compromised maintainer | High (write access to awesome-ai) | Backdoor injection, credential harvesting |
| MITM attacker | Medium (network position) | Plugin content tampering |
| Confused deputy | Low (misconfigured consumer) | Unintended privilege escalation |

### Attack Vectors

#### STRIDE Analysis

| Threat | Category | Impact | Likelihood | Mitigation |
|--------|----------|--------|------------|------------|
| Plugin repository takeover | Spoofing | Critical | Medium | SHA pinning, signature verification |
| Environment variable manipulation | Tampering | High | Medium | Path normalization, containment validation |
| Hook code injection | Elevation of Privilege | Critical | High | Sandboxing, permission model |
| CI template SHA bypass | Repudiation | High | High | Template validation, SHA enforcement |
| Secret exfiltration via plugin hooks | Information Disclosure | Critical | High | Secret masking, audit logging |
| Path traversal in AWESOME_AI_* vars | Tampering | High | Medium | GetFullPath normalization |
| Malicious plugin update | Denial of Service | Medium | Medium | Version pinning, rollback mechanism |
| Cross-plugin namespace collision | Elevation of Privilege | Medium | Low | Strict namespace validation |

---

## Findings

### Critical Findings

#### C-001: No Plugin Integrity Verification

**CWE-494**: Download of Code Without Integrity Check

**Location**: ADR-045 Path Abstraction section, line 69-71

**Description**: The ADR relies on Claude Code's plugin marketplace for distribution but does not specify any integrity verification mechanism. Plugins fetched from GitHub repos can be modified after initial review.

**Impact**: Compromised plugin maintainer or MITM attacker can inject malicious code into hooks, skills, or CI templates. Consumer projects automatically execute this code during session lifecycle.

**Evidence**:

```python
# From ADR-045
SESSION_DIR = os.environ.get("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")
```

No signature verification, checksum validation, or cryptographic attestation of plugin authenticity.

**CVSS Score**: 8.1 (High) - AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:N

**Remediation**:

1. **Require SHA pinning** for plugin sources in settings.json:

```json
{
  "extraKnownMarketplaces": {
    "awesome-ai": {
      "source": {
        "source": "github",
        "repo": "rjmurillo/awesome-ai",
        "ref": "v0.4.0",
        "sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"  // REQUIRED
      }
    }
  }
}
```

2. **Document signature verification** in Phase 0 (ADR section: Implementation):
   - Generate PGP signature for each release tag
   - Publish public key in repo root (KEYS file)
   - Add verification step to plugin installation docs

3. **Add supply chain ADR reference** to ADR-045 Consequences section:
   - Document threat model for plugin distribution
   - Define update verification protocol
   - Specify rollback procedure for compromised plugins

**Priority**: P0 (Blocking)

---

#### C-002: Hook Code Execution Without Sandboxing

**CWE-094**: Improper Control of Generation of Code

**Location**: Phase 3 Session Protocol Plugin, line 337-360

**Description**: Hooks from plugins execute with full privileges of the consumer project's runtime environment. No isolation, permission restrictions, or capability-based security model is defined.

**Impact**: Malicious plugin hook can:

- Read consumer project secrets (environment variables, .env files)
- Modify source code (via Write tool access)
- Exfiltrate data (HTTP requests to attacker-controlled servers)
- Execute arbitrary commands (via subprocess in Python hooks)

**Evidence**:

From ADR-045 hooks.json format:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/post-write.py"
      }
    ]
  }
}
```

Script runs with FULL filesystem access, network access, and environment variable visibility. No restrictions documented.

**CVSS Score**: 9.1 (Critical) - AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:L

**Remediation**:

1. **Define permission model** for plugin hooks (add to ADR-045 Design Decisions):

```markdown
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Hook permissions | Least privilege by default | Hooks declare required capabilities in manifest |
```

2. **Add capabilities to plugin.json schema**:

```json
{
  "name": "session-protocol",
  "capabilities": {
    "filesystem": ["read:.agents/sessions/*", "write:.agents/sessions/*"],
    "environment": ["read:AWESOME_AI_*"],
    "network": "deny"
  }
}
```

3. **Document security boundary** in Phase 0 Foundation (new section):

```markdown
### Hook Security Model

Hooks execute in consumer project context with restricted capabilities:

- **Filesystem**: Access limited to paths declared in capabilities
- **Network**: Deny by default, explicit allow required
- **Environment**: Read-only access to AWESOME_AI_* and CLAUDE_* variables
- **Secrets**: .env files, git credentials, SSH keys BLOCKED by default
```

**Priority**: P0 (Blocking)

---

### High Findings

#### H-001: Path Traversal via Environment Variables

**CWE-22**: Improper Limitation of a Pathname to a Restricted Directory

**Location**: ADR-045 Path Abstraction Contract, line 232-241

**Description**: Environment variables for consumer paths (AWESOME_AI_SESSIONS_DIR, etc.) are used directly without normalization or containment validation. An attacker who controls these variables can traverse to arbitrary filesystem locations.

**Impact**: Malicious consumer (or compromised CI environment) can:

- Point AWESOME_AI_SESSIONS_DIR to `/etc` to read system configs
- Point AWESOME_AI_HANDOFF_PATH to `/home/user/.ssh/id_rsa` to exfiltrate keys
- Use `../../` sequences to escape intended directories

**Evidence**:

From ADR-045:

```python
SESSION_DIR = os.environ.get("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")
```

From existing PowerShell script (Post-PRCommentReply.ps1):

```powershell
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8  # No path validation
}
```

**Attack Scenario**:

```bash
export AWESOME_AI_SESSIONS_DIR="../../home/user/.ssh"
# Plugin reads ".agents/sessions/session.json"
# Actual path resolves to: /home/user/.ssh/session.json
```

**CVSS Score**: 7.8 (High) - AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H

**Remediation**:

1. **Add path normalization** to ADR-045 Path Abstraction Contract section:

```python
import os
from pathlib import Path

def get_safe_path(env_var: str, default: str, base_dir: str = ".") -> Path:
    """
    Get path from environment variable with security validation.

    Args:
        env_var: Environment variable name
        default: Default relative path
        base_dir: Base directory for containment (default: current working directory)

    Returns:
        Validated absolute path

    Raises:
        ValueError: If path escapes base directory or contains invalid characters
    """
    # Get path from environment or use default
    path_str = os.environ.get(env_var, default)

    # Normalize to absolute path
    base = Path(base_dir).resolve()
    target = (base / path_str).resolve()

    # Verify containment
    if not target.is_relative_to(base):
        raise ValueError(
            f"Path traversal detected: {env_var}={path_str} resolves to "
            f"{target} which is outside allowed directory {base}"
        )

    return target

# Usage in plugin code
SESSION_DIR = get_safe_path("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")
```

2. **Update Phase 2 Path Parameterization Pattern** with secure example.

3. **Add verification checklist** to Phase 2:

```markdown
- [ ] All path environment variables use GetFullPath/resolve() normalization
- [ ] Containment validation prevents `..` traversal
- [ ] Symlink resolution checked (detect symlink escapes)
- [ ] Path length limits enforced (prevent buffer overflows)
```

**Priority**: P0 (Blocking)

---

#### H-002: CI Workflow Templates Without SHA Pinning Enforcement

**CWE-829**: Inclusion of Functionality from Untrusted Control Sphere

**Location**: Phase 3 Quality Gates Plugin, line 362-376

**Description**: Quality gates plugin distributes CI workflow templates as consumable references. The ADR does not mandate SHA pinning for actions within these templates, creating supply chain vulnerability.

**Impact**: Consumer projects copy workflow templates from plugin without SHA-pinned actions. Template author (or compromised awesome-ai maintainer) can reference mutable tags (@v4) that attackers can hijack.

**Evidence**:

From PROJECT-CONSTRAINTS.md (existing security constraint):

```markdown
| MUST pin GitHub Actions to commit SHA | security-practices | Pre-commit hook blocks |
```

But ADR-045 Phase 3 does not reference this requirement for distributed templates.

**Attack Scenario**:

1. awesome-ai distributes workflow template:

```yaml
# .github/workflows/quality-gate-template.yml (in plugin)
- uses: actions/checkout@v4  # MUTABLE TAG
```

2. Consumer copies template without modification
3. Attacker compromises actions/checkout maintainer
4. Attacker moves v4 tag to malicious commit
5. All consumers now execute attacker code

**CVSS Score**: 7.4 (High) - AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:N

**Remediation**:

1. **Add SHA pinning requirement** to Phase 3 Quality Gates Plugin:

```markdown
### CI Workflow Templates

| Component | Source | Count | Security Requirement |
|-----------|--------|-------|---------------------|
| CI workflow templates | `.github/workflows/` (framework) | ~5 | **MUST** use SHA-pinned actions |

**Template Security Requirements**:

- All `uses:` directives MUST use commit SHA with version comment
- Pattern: `uses: owner/action@{40-char-sha} # v{version}`
- Pre-commit hook in awesome-ai enforces SHA pinning
- Templates include header comment documenting security requirements
```

2. **Add pre-commit hook** to awesome-ai repo (Phase 0):

```python
# .github/hooks/pre-commit
"""
Validate workflow templates for SHA-pinned actions.
Blocks commits with mutable version tags.
"""
import re
import sys

def validate_workflow(file_path):
    with open(file_path) as f:
        content = f.read()

    # Pattern: uses: owner/repo@SOMETHING
    pattern = r'uses:\s+[\w-]+/[\w-]+@(\S+)'
    matches = re.finditer(pattern, content)

    for match in matches:
        ref = match.group(1)
        # Check if ref is 40-char hex (SHA) or mutable tag
        if not re.match(r'^[a-f0-9]{40}$', ref):
            print(f"ERROR: Mutable action reference in {file_path}: {match.group(0)}")
            print(f"       Required: SHA-pinned reference (40-char hex)")
            return False

    return True
```

3. **Update Phase 5 Documentation** to include template security guide:

```markdown
### Consuming Workflow Templates Safely

awesome-ai workflow templates follow security best practices:

- Actions pinned to immutable commit SHAs
- Version comments for maintainability
- No secrets in workflow definitions

When copying templates:
1. Verify SHA pins are intact
2. Review for project-specific modifications
3. Run local validation: `gh act --dryrun`
```

**Priority**: P1 (Must address before release)

---

#### H-003: No Secret Masking in Plugin Hooks

**CWE-532**: Insertion of Sensitive Information into Log File

**Location**: Phase 3 Session Protocol Plugin, hooks execution context

**Description**: Plugin hooks execute with access to consumer environment variables and can log or transmit secrets without detection. No secret masking, audit logging, or sensitive data filtering is specified.

**Impact**: Plugin hook accidentally (or intentionally) logs credentials:

```python
# Malicious or poorly-written hook
import os
import logging

logging.info(f"Environment: {os.environ}")  # Logs ALL env vars including secrets
```

Secrets exposed in:
- Claude Code session transcripts
- CI logs (GitHub Actions)
- Local log files

**Evidence**:

From ADR-045 hooks.json format (no mention of secret handling):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py"
      }
    ]
  }
}
```

**CVSS Score**: 6.8 (Medium) - AV:N/AC:H/PR:L/UI:N/S:U/C:H/I:N/A:N

**Remediation**:

1. **Add secret masking requirement** to Phase 3 Hook Security section:

```markdown
### Hook Security Requirements

Hooks MUST NOT log or transmit:

- Environment variables matching `.*KEY$`, `.*SECRET$`, `.*TOKEN$`, `.*PASSWORD$`
- File contents from `.env`, `.env.*`, `credentials.json`, `*.pem`, `*.key`
- Git credentials, SSH keys, API tokens

**Secret Masking Implementation**:

Plugins include `SecretFilter` utility:

```python
# ${CLAUDE_PLUGIN_ROOT}/utils/secret_filter.py
import re
import os

SECRET_PATTERNS = [
    (r'[A-Z0-9_]*KEY[A-Z0-9_]*', 'environment variable'),
    (r'[A-Z0-9_]*SECRET[A-Z0-9_]*', 'environment variable'),
    (r'[A-Z0-9_]*TOKEN[A-Z0-9_]*', 'environment variable'),
    (r'[A-Z0-9_]*PASSWORD[A-Z0-9_]*', 'environment variable'),
    (r'-----BEGIN .* PRIVATE KEY-----', 'private key'),
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub token'),
    (r'sk-[a-zA-Z0-9]{48}', 'OpenAI API key'),
]

def mask_secrets(text: str) -> str:
    """Replace secrets with masked placeholders."""
    for pattern, label in SECRET_PATTERNS:
        text = re.sub(pattern, f'***{label.upper()}***', text, flags=re.IGNORECASE)
    return text

def safe_log(message: str):
    """Log message with secrets masked."""
    print(mask_secrets(message))
```

**Hook Testing Requirement**:

All hook scripts MUST pass secret leak detection before merge:

```bash
# Test hook for secret exposure
pytest tests/security/test_secret_masking.py
```
```

2. **Add verification to Phase 3 checklist**:

```markdown
- [ ] All hooks use SecretFilter for logging
- [ ] Secret leak tests pass
- [ ] No environment variable dumps in hook code
```

**Priority**: P1 (Must address before release)

---

#### H-004: Plugin Update Without Rollback Mechanism

**CWE-494**: Download of Code Without Integrity Check (update scenario)

**Location**: ADR-045 Rationale, Versioning Strategy (line 86-88)

**Description**: The ADR specifies version pinning (v0.4.0) but does not define rollback procedure if a plugin update introduces security vulnerability or breaking change.

**Impact**: Consumer projects auto-update to compromised plugin version with no documented recovery path. Incident response delayed while teams manually revert changes.

**Evidence**:

From ADR-045:

```markdown
awesome-ai starts at v0.4.0, aligned with the ai-agents milestone.
```

No mention of:
- Update verification
- Rollback commands
- Version pinning strategy for consumers
- Breaking change policy

**CVSS Score**: 6.2 (Medium) - AV:N/AC:H/PR:N/UI:R/S:U/C:N/I:H/A:L

**Remediation**:

1. **Add rollback procedure** to Phase 5 Documentation:

```markdown
### Plugin Update Safety

**Version Pinning for Stability**:

Lock to specific version in settings.json:

```json
{
  "extraKnownMarketplaces": {
    "awesome-ai": {
      "source": {
        "source": "github",
        "repo": "rjmurillo/awesome-ai",
        "ref": "v0.4.0",  // Pin to known-good version
        "sha": "abc123..."
      }
    }
  }
}
```

**Rollback Procedure**:

If plugin update causes issues:

1. Identify last known-good version: Check git log in awesome-ai repo
2. Update settings.json with previous version SHA
3. Clear plugin cache: `rm -rf ~/.claude/plugin-cache/awesome-ai`
4. Reinstall: `/plugin marketplace update`
5. Verify: `/plugin validate .`

**Testing Updates Before Deployment**:

```bash
# Create test branch
git checkout -b test-plugin-update

# Update to new version in settings.json
vim .claude/settings.json

# Test session lifecycle
pwsh scripts/Test-SessionLifecycle.ps1

# If tests pass, merge to main
git checkout main && git merge test-plugin-update
```
```

2. **Add breaking change policy** to awesome-ai governance:

```markdown
### Semantic Versioning for Security

awesome-ai follows semantic versioning with security extensions:

- **Patch** (v0.4.1): Bug fixes, no breaking changes, security patches
- **Minor** (v0.5.0): New features, backward compatible, security enhancements
- **Major** (v1.0.0): Breaking changes, incompatible API changes

**Security Release Policy**:

- Critical vulnerabilities: Patch released within 48 hours
- High vulnerabilities: Patch released within 7 days
- All releases signed with PGP key
- Security advisories published to GitHub Security tab
```

**Priority**: P1 (Must address before release)

---

### Medium Findings

#### M-001: Cross-Plugin Namespace Collision Risk

**CWE-1188**: Initialization of a Resource with an Insecure Default

**Location**: ADR-045 Namespace Impact (line 75-83)

**Description**: Plugin namespacing (/awesome-ai:skill-name) prevents collisions between plugins, but the ADR does not specify validation for plugin names or enforcement of namespace uniqueness.

**Impact**: Malicious actor publishes plugin with name collision (e.g., awesome-ai-malicious) to confuse users or hijack skill invocations.

**CVSS Score**: 4.8 (Medium) - AV:N/AC:H/PR:L/UI:R/S:U/C:L/I:L/A:L

**Remediation**:

Add to Phase 0 Foundation:

```markdown
### Namespace Validation

Plugin names MUST:
- Follow regex: `^[a-z0-9]+(-[a-z0-9]+)*$` (kebab-case, alphanumeric)
- Not collide with reserved prefixes: `claude-`, `anthropic-`, `builtin-`
- Not collide with existing plugin names in marketplace

Validation enforced by:
- Pre-commit hook in awesome-ai repo
- Claude Code plugin validation command
- Marketplace manifest schema validation
```

**Priority**: P2 (Nice to have)

---

#### M-002: No Audit Logging for Hook Execution

**CWE-778**: Insufficient Logging

**Location**: Phase 3 Session Protocol Plugin

**Description**: Hooks execute code in consumer environment but no audit trail documents which hooks ran, when, and with what permissions.

**Impact**: Security incident investigation lacks forensic data. Cannot determine if malicious plugin hook executed or what it accessed.

**CVSS Score**: 4.1 (Medium) - AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N

**Remediation**:

Add to Phase 3 Session Protocol Plugin:

```markdown
### Hook Audit Logging

**Log Format** (append to `.agents/sessions/hooks.log`):

```json
{
  "timestamp": "2026-02-07T10:23:45Z",
  "hook_type": "PostToolUse",
  "plugin": "awesome-ai:session-protocol",
  "script": "${CLAUDE_PLUGIN_ROOT}/hooks/post-write.py",
  "exit_code": 0,
  "duration_ms": 123,
  "matched_tool": "Write"
}
```

**Log Retention**: 30 days, rotated daily

**Security Events Logged**:
- Hook execution start/end
- Exit code (0=success, 2=blocking error)
- Tool matcher pattern
- Plugin namespace

**No Secrets Logged**:
- Environment variables
- File contents
- Tool parameters
```

**Priority**: P2 (Nice to have)

---

#### M-003: Python Migration Dependency Not Security-Reviewed

**CWE-1104**: Use of Unmaintained Third Party Components

**Location**: ADR-045 Prerequisites (line 36)

**Description**: The ADR states v0.3.1 (PowerShell-to-Python migration) must complete before extraction, but does not link to security review of migrated Python code.

**Impact**: Python scripts extracted to awesome-ai may contain vulnerabilities introduced during migration (e.g., subprocess injection, insecure deserialization).

**CVSS Score**: 4.6 (Medium) - AV:N/AC:L/PR:L/UI:R/S:U/C:L/I:L/A:N

**Remediation**:

Add to Phase 0 Foundation:

```markdown
### Prerequisites Security Verification

Before Phase 1 extraction begins:

- [ ] v0.3.1 Python migration COMPLETE
- [ ] Security review of migrated Python code APPROVED
- [ ] Python security checklist verified (`.agents/security/python-security-checklist.md`)
- [ ] No CWE-78 (subprocess injection) findings in migrated scripts
- [ ] No CWE-502 (insecure deserialization) findings in migrated scripts

Verification:
```bash
# Run Python security scanners
bandit -r scripts/ -ll  # High and Medium severity
semgrep --config=p/python scripts/
```

**Blocking Gate**: Do not proceed to Phase 1 until Python security review exits with 0 critical/high findings.
```

**Priority**: P2 (Must verify before execution)

---

## Security Controls Assessment

### Authentication

| Control | Status | Notes |
|---------|--------|-------|
| Plugin source authentication | ❌ | GitHub authentication assumed but not verified |
| Plugin signature verification | ❌ | No PGP/GPG signature requirement |
| Marketplace catalog integrity | ❌ | No checksum for marketplace.json |
| SHA pinning for plugin versions | ⚠️ | Mentioned but not enforced |

### Authorization

| Control | Status | Notes |
|---------|--------|-------|
| Hook permission model | ❌ | Full privileges, no capability restrictions |
| Filesystem access control | ❌ | Hooks can read/write any file |
| Network access control | ❌ | Hooks can make arbitrary HTTP requests |
| Environment variable access | ⚠️ | Read-only implied but not enforced |

### Data Protection

| Control | Status | Notes |
|---------|--------|-------|
| Path traversal prevention | ❌ | No normalization specified |
| Secret masking in logs | ❌ | Hooks can log sensitive data |
| .env file protection | ❌ | Hooks can read .env files |
| Credential isolation | ❌ | No boundary between plugin and consumer secrets |

### Logging and Monitoring

| Control | Status | Notes |
|---------|--------|-------|
| Hook execution audit trail | ❌ | No logging specified |
| Security event logging | ❌ | No monitoring for suspicious plugin behavior |
| Anomaly detection | ❌ | No baseline for normal plugin activity |
| Incident response | ❌ | No rollback procedure documented |

**Legend**: ✅ Implemented | ⚠️ Partial | ❌ Missing

---

## Dependency Security

### awesome-ai Dependencies

| Dependency | Version | Known CVEs | Risk Level | Action |
|------------|---------|------------|------------|--------|
| Claude Code runtime | Latest | None known | Low | Monitor security advisories |
| Python 3.x | TBD | CVE-2024-XXXX (example) | Medium | Pin to patched version |
| PowerShell 7.x | TBD | None known | Low | Use latest stable |
| GitHub Actions | Various | SHA-pinned required | High | Enforce SHA pinning |

**Transitive Dependencies**: Not analyzed (Python packages not yet defined post-v0.3.1)

**Action Required**: Add dependency security scan to Phase 0:

```bash
# Python dependencies
pip install safety
safety check

# PowerShell modules
Install-Module -Name PSScriptAnalyzer
Invoke-ScriptAnalyzer -Path . -Recurse -Severity Warning
```

---

## Recommendations

### Immediate Actions (P0)

1. **Add supply chain security section** to ADR-045:
   - Define SHA pinning requirement for plugin sources
   - Document signature verification for releases
   - Specify integrity verification mechanism

2. **Define hook permission model** with least privilege:
   - Capabilities declared in plugin.json
   - Filesystem, network, environment access restrictions
   - Default deny for sensitive resources

3. **Implement path security** for environment variables:
   - Add get_safe_path utility with normalization
   - Validate containment within base directory
   - Detect symlink escapes

4. **Enforce SHA pinning in CI templates**:
   - Add pre-commit hook to awesome-ai
   - Validate all workflow templates
   - Document template security requirements

### Short-term Actions (P1)

1. **Add secret masking** for plugin hooks:
   - Implement SecretFilter utility
   - Require secret leak tests
   - Document safe logging practices

2. **Document rollback procedure**:
   - Version pinning strategy
   - Rollback commands
   - Testing workflow for updates

3. **Add security verification** to Phase 0:
   - v0.3.1 Python migration security review
   - Python security checklist verification
   - Bandit/Semgrep scan requirement

### Long-term Actions (P2)

1. **Implement namespace validation**:
   - Enforce kebab-case naming
   - Prevent reserved prefix usage
   - Validate uniqueness in marketplace

2. **Add audit logging** for hook execution:
   - Log format specification
   - 30-day retention policy
   - Security event monitoring

3. **Create security test suite** for awesome-ai:
   - Path traversal tests
   - Secret leak detection
   - Hook permission boundary tests

---

## Blast Radius Assessment

| If Control Fails | Systems Affected | Data at Risk | Containment Strategy |
|------------------|------------------|--------------|---------------------|
| Plugin repository compromise | All consumers of awesome-ai | Source code, secrets, credentials | SHA pinning, signature verification, version lockdown |
| Path traversal in env vars | Single consumer project | Project files, config, limited to process privileges | Normalization, containment validation, least privilege |
| Hook code injection | Single consumer project | Session data, git history, limited to user privileges | Permission model, sandboxing, audit logging |
| CI template without SHA pins | Consumers copying templates | CI secrets, deployment credentials | Template validation, pre-commit hooks, documentation |

**Worst Case Impact**: Malicious plugin with compromised hooks executes in all consumer projects consuming awesome-ai. Attacker gains access to source code, credentials, and CI/CD pipelines of all consumers.

**Isolation Boundaries**:

- Plugin cache isolation (${CLAUDE_PLUGIN_ROOT}) limits cross-consumer contamination
- Consumer project privileges limit blast radius to single organization
- Git-based distribution provides audit trail and rollback capability

---

## Compliance Implications

### Project Constraints (PROJECT-CONSTRAINTS.md)

| Constraint | Compliance | Finding |
|------------|------------|---------|
| MUST pin GitHub Actions to commit SHA | ❌ | H-002: CI templates lack SHA enforcement |
| MUST NOT put logic in workflow YAML | ✅ | Templates delegate to scripts |
| MUST initialize Serena before action | ✅ | Session protocol maintains requirement |

### OWASP Top 10 (2021)

| Category | Risk | Finding |
|----------|------|---------|
| A03:2021 Injection | High | H-001: Path traversal via env vars |
| A08:2021 Software Integrity | Critical | C-001: No integrity verification |
| A09:2021 Security Logging | Medium | M-002: No audit logging |

### OWASP Agentic Top 10 (2026)

| Category | Risk | Finding |
|----------|------|---------|
| ASI02: Tool Misuse | High | C-002: No hook sandboxing |
| ASI03: Identity Abuse | High | H-003: Secret exposure risk |
| ASI04: Supply Chain | Critical | C-001: Plugin integrity |

---

## Verification Tests

| Test Type | Status | Coverage |
|-----------|--------|----------|
| Unit tests (path security) | ❌ | 0% (not specified) |
| Integration tests (hook execution) | ❌ | 0% (not specified) |
| Security tests (secret leak) | ❌ | 0% (not specified) |
| Supply chain tests (SHA validation) | ❌ | 0% (not specified) |

**Required Test Suite** (add to Phase 0):

```python
# tests/security/test_path_security.py
def test_path_traversal_blocked():
    """Verify environment variables cannot escape base directory."""
    os.environ["AWESOME_AI_SESSIONS_DIR"] = "../../etc"
    with pytest.raises(ValueError, match="Path traversal"):
        get_safe_path("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")

def test_symlink_escape_blocked():
    """Verify symlinks cannot escape base directory."""
    os.symlink("/etc/passwd", ".agents/sessions/escape")
    with pytest.raises(ValueError, match="Symlink escape"):
        get_safe_path("AWESOME_AI_SESSIONS_DIR", ".agents/sessions/escape")

# tests/security/test_secret_masking.py
def test_environment_variables_masked():
    """Verify secrets not logged by hooks."""
    os.environ["GITHUB_TOKEN"] = "ghp_secret123"
    output = run_hook("session-start.py")
    assert "ghp_secret123" not in output
    assert "***GITHUB_TOKEN***" in output

# tests/security/test_hook_permissions.py
def test_hook_cannot_read_env_file():
    """Verify hooks blocked from .env access."""
    with pytest.raises(PermissionError):
        run_hook_with_file_access("malicious-hook.py", ".env")
```

---

## Deviations from Plan

| Planned Security Control | Implementation Status | Justification |
|--------------------------|----------------------|---------------|
| SHA pinning | Mentioned but not enforced | **MUST IMPLEMENT** (P0) |
| Hook permission model | Not specified | **MUST DEFINE** (P0) |
| Path normalization | Not specified | **MUST IMPLEMENT** (P0) |
| Secret masking | Not specified | SHOULD IMPLEMENT (P1) |
| Audit logging | Not specified | MAY IMPLEMENT (P2) |

---

## Recommendation

**NEEDS-REVISION**

ADR-045 provides strong architectural vision for framework extraction but lacks critical security controls for plugin distribution and execution.

### Required Actions Before Acceptance

1. **Address P0 findings** (4 critical/high issues):
   - C-001: Add supply chain security (SHA pinning, signatures)
   - C-002: Define hook permission model with sandboxing
   - H-001: Implement path security with normalization
   - H-002: Enforce SHA pinning in CI templates

2. **Update ADR sections**:
   - Add "Security Model" section after Design Decisions
   - Expand Phase 0 with security verification requirements
   - Add security checklist to Phase 2, 3, and 4 verification

3. **Create security documentation**:
   - Hook Security Guidelines (for plugin authors)
   - Consumer Security Guide (for projects using awesome-ai)
   - Security Incident Response (rollback, reporting)

### Conditional Acceptance Criteria

✅ **APPROVED** if:
- P0 findings resolved with concrete implementations
- Security Model section added to ADR
- Hook permission model defined and testable
- Path security utility implemented with tests
- SHA pinning enforced in CI templates

❌ **REJECTED** if:
- Supply chain security remains unaddressed
- Hook execution retains full consumer privileges
- Path traversal risk not mitigated

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Security Reviewer | Security Agent | 2026-02-07 | **NEEDS-REVISION** |
| Architect | [Pending] | [Pending] | [Pending] |
| ADR Author | [Pending] | [Pending] | [Pending] |

---

## Related Documents

- [ADR-045: Framework Extraction via Plugin Marketplace](../architecture/ADR-045-framework-extraction-via-plugin-marketplace.md)
- [v0.4.0 Implementation Plan](../projects/v0.4.0/PLAN.md)
- [PROJECT-CONSTRAINTS.md](../governance/PROJECT-CONSTRAINTS.md)
- [Python Security Checklist](python-security-checklist.md)
- [Security Best Practices](security-best-practices.md)
- [Architecture Security Template](architecture-security-template.md)

---

*Security Review Version: 1.0*
*CWE Taxonomy: 4.13*
*OWASP: Top 10 2021, Agentic Top 10 2026*
