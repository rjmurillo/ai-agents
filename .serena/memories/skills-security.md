# Security Skills

**Extracted**: 2025-12-16
**Source**: `.agents/retrospective/phase1-remediation-pr43.md`

## Skill-Security-001: Multi-Agent Security Validation Chain

**Statement**: Security findings require three-agent validation: security analysis → qa verification → devops compatibility check

**Context**: When remediating security vulnerabilities

**Evidence**: Session 44 used Security → QA → DevOps chain, all passed, remediation successful

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 9/10

**Updated**: 2025-12-20 (expanded from two-phase to three-agent validation)

**Pattern**:

```text
Security Agent:
  - Threat analysis
  - Remediation plan (SR-XXX report)
  ↓
QA Agent:
  - Syntax validation
  - Acceptance criteria verification
  - QA report
  ↓
DevOps Agent:
  - CI compatibility check
  - Build time impact assessment
  - Platform availability verification
  ↓
Implementer:
  - Apply remediation
  - Commit with all three reports
```

**Original Two-Phase Pattern** (still valid for planning):

```text
Phase 1 (Pre-Implementation):
  security agent → Threat model, required controls, security requirements
  
Phase 2 (Implementation):  
  implementer → Code + flag security-relevant changes for review
  
Phase 3 (Post-Implementation):
  security agent → Verify controls implemented, actual code review
```

**Anti-Pattern**:

- Single security review at planning time only
- Security not re-engaged after implementation
- No handoff from implementer back to security
- Single-agent security review without downstream validation

---

---

## Skill-Security-002: Input Validation First (88%)

**Statement**: Always validate and sanitize inputs before processing

**Context**: Any code handling external data

**Evidence**: Security best practices document in governance

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 9/10

**Strategy**:

- Parameterized queries for database access
- Allowlists over denylists for input validation
- Type checking before processing

**Source**: `.agents/security/security-best-practices.md`

---

## Skill-Security-003: Secure Error Handling (90%)

**Statement**: Never expose stack traces or internal details in errors

**Context**: Error handling in any user-facing code

**Evidence**: Security best practices document

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

- Generic messages to external users
- Detailed logs internal only
- Correlation IDs for debugging

**Source**: `.agents/security/security-best-practices.md`

---

## Skill-Security-004: Security Event Logging (85%)

**Statement**: Log security events with context but without sensitive data

**Context**: Authentication, access control, data changes

**Evidence**: Security best practices document

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 8/10

**Events to Log**:

- Authentication attempts (success/failure)
- Authorization decisions
- Data modifications
- Configuration changes

**Source**: `.agents/security/security-best-practices.md`

---

## Skill-Security-005: Regex-Based Secret Detection (92%)

**Statement**: Use regex patterns to detect hardcoded secrets in code

**Context**: Pre-commit hooks, PR gates, security scans

**Evidence**: Secret detection patterns document with regex library

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Pattern Categories**:

- AWS keys: `AKIA[0-9A-Z]{16}`
- GitHub tokens: `gh[ps]_[A-Za-z0-9]{36}`
- Connection strings: `(password|pwd)=[^;]+`
- API keys: `(api_key|apikey)=[A-Za-z0-9]+`

**Source**: `.agents/security/secret-detection-patterns.md`

---

## Skill-Security-006: Infrastructure File Categories (88%)

**Statement**: Target security reviews on 8 categories of security-sensitive files

**Context**: Security review scoping and prioritization

**Evidence**: Infrastructure file patterns document

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Categories**:

1. CI/CD: `*.yml`, `*.yaml` in `.github/`, `.gitlab-ci/`
2. IaC: `*.tf`, `*.tfvars`, `*.bicep`, `*.arm.json`
3. Docker: `Dockerfile*`, `docker-compose*.yml`
4. Kubernetes: `*.yaml` in `k8s/`, `helm/`
5. Scripts: `*.sh`, `*.ps1`, `*.bat`
6. Configs: `*.config`, `*.conf`, `*.ini`
7. Cloud: `*.aws`, `*.azure`, `*.gcp`
8. Network: firewall rules, security groups

**Source**: `.agents/security/infrastructure-file-patterns.md`

---

## Skill-Security-007: Defense-in-Depth for Cross-Process Security Checks (94%)

**Statement**: Always re-validate security conditions in the process that performs the action, even if validation occurred in a child process

**Context**: When security validation (symlink check, path validation) runs in a subprocess and a subsequent action (file write, git add) runs in the parent

**Evidence**: PR #52 - PowerShell symlink check insufficient due to TOCTOU race window between pwsh completion and bash git add

**Atomicity**: 94%

**Tag**: helpful (security)

**Impact**: 9/10

**Pattern**:

```bash
# Child process validates
RESULT=$(pwsh -File sync-script.ps1)  # Symlink check here

# Parent MUST re-validate before action
if [ -L "$FILE" ]; then               # Defense-in-depth check
    echo "Error: symlink"
else
    git add -- "$FILE"                # Action in same process as check
fi
```

**Anti-Pattern**:

- Trusting child process security checks without re-validation
- Performing action in different process than security check

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

---

## Skill-Security-008: First-Run Gap Analysis (91%)

**Statement**: When reviewing conditional security checks, verify they cover creation scenarios, not just modification scenarios

**Context**: When security code uses existence checks (`if file exists then validate`)

**Evidence**: PR #52 - `if (Test-Path $DestinationPath)` meant symlink check only ran on updates, not creates

**Atomicity**: 91%

**Tag**: helpful (security)

**Impact**: 8/10

**Pattern**:

```powershell
# WRONG: Only validates when file exists
if (Test-Path $Path) {
    if ((Get-Item $Path).LinkType) { throw "symlink" }
}
# First-run creates file without validation!

# RIGHT: Validate after creation too
$result = Create-File $Path
if ((Get-Item $Path).LinkType) { throw "symlink" }
```

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

---

## Skill-Security-009: Domain-Adjusted Signal Quality for Security Comments (88%)

**Statement**: Security review comments from any reviewer have higher actionability than style suggestions - adjust triage priority accordingly

**Context**: When triaging bot review comments on security-sensitive files

**Evidence**: PR #52 - CodeRabbit style suggestions ~30% actionable overall, but security suggestion on .githooks was 100% valid (TOCTOU vulnerability)

**Atomicity**: 88%

**Tag**: helpful (triage)

**Impact**: 7/10

**Heuristic**:

| Comment Domain | Base Signal | Adjustment |
|----------------|-------------|------------|
| Bug report | Use base | No change |
| Style suggestion | Use base | No change |
| Security issue | +40% | Always investigate |
| .githooks file | +50% | ASSERTIVE ENFORCEMENT required |

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

---

## Skill-Security-010: Pre-Commit Bash Detection (95%)

**Statement**: Enforce ADR-005 with pre-commit hook rejecting bash in `.github/workflows/` and `.github/scripts/`

**Context**: When implementing or reviewing workflow files

**Evidence**: PR #60 bash code caused CWE-20/CWE-78, would have been caught by grep-based hook

**Atomicity**: 95%

**Tag**: helpful (security)

**Impact**: 9/10

**Created**: 2025-12-20

**Pattern**:

```bash
# Pre-commit hook (.githooks/pre-commit)
if git diff --cached --name-only | grep -E '^\.github/(workflows|scripts)/.*\.(yml|yaml)$'; then
    if git diff --cached | grep -E '^\+.*shell: bash'; then
        echo "ERROR: Bash not allowed in workflows (ADR-005). Use PowerShell (pwsh)."
        exit 1
    fi
fi
```

**Anti-Pattern**: Trusting manual review to catch ADR violations

**Source**: `.agents/retrospective/2025-12-20-pr-211-security-miss.md`

---

## Related Documents

- Source: `.agents/retrospective/phase1-remediation-pr43.md`
- Source: `.agents/retrospective/pr-52-symlink-retrospective.md`
- Source: `.agents/security/security-best-practices.md`
- Source: `.agents/security/secret-detection-patterns.md`
- Source: `.agents/security/infrastructure-file-patterns.md`
- Issue: #I7 in retrospective
- Related: skills-process-workflow-gaps (workflow patterns)
- Related: pr-comment-responder-skills (triage patterns)
