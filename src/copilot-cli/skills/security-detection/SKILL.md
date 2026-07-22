---
name: security-detection
description: Detect infrastructure and security-critical file changes to trigger security agent review recommendations ensuring proper security oversight for sensitive modifications. Use when you ask "did I touch security-critical files", "should the security agent review this". Detection only. Do NOT use to scan source for injection patterns (use security-scan).
license: MIT
metadata:
version: 1.0.0
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
---

# Security Detection Utility

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `scan for security changes` | detect-infrastructure with staged files |
| `check security-critical files` | detect-infrastructure with file list |
| `run security scan on changes` | detect-infrastructure analysis |
| `do I need a security review` | Risk-level assessment of changed files |
| `check infrastructure changes` | Pattern matching against critical/high lists |

---

## When to Use

Use this skill when:

- Committing changes that may touch infrastructure or security files
- Pre-commit validation for security-sensitive paths
- Determining if a security agent review is needed
- CI pipeline security gate checks

Use the security agent directly instead when:

- You already know security review is needed
- Performing threat modeling or vulnerability assessment
- Reviewing authentication or authorization code in depth

---

## Available Scripts

| Script | Language | Usage |
|--------|----------|-------|
| `detect_infrastructure.py` | Python 3 | Cross-platform |

## Usage

```bash
# Analyze staged files
python detect_infrastructure.py --use-git-staged

# Analyze specific files
python detect_infrastructure.py --files .github/workflows/ci.yml src/auth/login.cs
```

## Output

When security-critical files are detected:

```text
=== Security Review Detection ===

CRITICAL: Security agent review REQUIRED

Matching files:
  [CRITICAL] .github/workflows/deploy.yml
  [HIGH] src/Controllers/AuthController.cs

Run security agent before implementation:
  `agent_type: "project-toolkit:security"` with prompt "Review infrastructure changes"
```

When no matches:

```text
No infrastructure/security files detected.
```

## Risk Levels

| Level | Meaning | Action |
|-------|---------|--------|
| CRITICAL | Immediate security implications | Review REQUIRED |
| HIGH | Potential security impact | Review RECOMMENDED |

## Detected Patterns

### Critical (Review Required)

- CI/CD workflows (`.github/workflows/*`)
- Git hook configuration (`{lefthook,.lefthook,lefthook-local,.lefthook-local}.{yml,yaml,json,jsonc,toml}`, `.config/{lefthook,lefthook-local}.{yml,yaml,json,jsonc,toml}`, `.husky/*`)
- Git hook policy (`scripts/validation/git_hook_policy.py`)
- Authentication code (`**/Auth/**`, `**/Security/**`)
- Environment files (`*.env*`)
- Credentials and keys (`*.pem`, `*.key`, `*secret*`)

### High (Review Recommended)

- Build scripts (`build/**/*.ps1`, `scripts/**/*.sh`)
- Container configs (`Dockerfile*`, `docker-compose*`)
- API controllers (`**/Controllers/**`)
- App configuration (`appsettings*.json`)
- Infrastructure as Code (`*.tf`, `*.tfvars`, `*.bicep`)

## Integration

### Pre-commit Hook

Add a named validator job to `lefthook.yml`:

```bash
# Security detection (non-blocking warning)
python3 .claude/skills/security-detection/detect_infrastructure.py --use-git-staged
```

### CI Integration

On a Linux pull-request runner, pass the changed paths explicitly. CI checkouts
do not have a staged diff.

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  with:
    fetch-depth: 0

- name: Check security-critical files
  shell: bash
  env:
    BASE_SHA: ${{ github.event.pull_request.base.sha }}
    HEAD_SHA: ${{ github.sha }}
  run: >-
    git diff --no-renames --name-only -z "$BASE_SHA" "$HEAD_SHA"
    | python .claude/skills/security-detection/detect_infrastructure.py
    --files-from-stdin
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (warning shown if matches found, non-blocking) |

The scripts are designed to be non-blocking warnings. They always exit 0 to avoid blocking commits or CI. The warning is informational only.

## Customization

Edit the pattern lists in either script to add or modify detection patterns:

- `CRITICAL_PATTERNS` / `$CriticalPatterns` - Review required
- `HIGH_PATTERNS` / `$HighPatterns` - Review recommended

## Process

1. Gather the list of changed files (staged or explicit)
2. Run pattern matching against critical and high-risk file patterns
3. Report findings with risk level classification
4. Route to security agent if CRITICAL matches found

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping detection before commits | Security files slip through unreviewed | Run detection on every commit with infrastructure changes |
| Treating warnings as blocking | Scripts exit 0 intentionally | Use output to inform review decisions, not block commits |
| Hardcoding custom patterns inline | Drifts from canonical pattern lists | Edit CRITICAL_PATTERNS/HIGH_PATTERNS in the scripts |
| Ignoring HIGH-level matches | Potential security impact overlooked | Review HIGH matches, escalate to security agent when uncertain |
| Running only one language script | May miss platform-specific detection | Use whichever script matches your environment |

---

## Verification

After running security detection:

- [ ] Script exited with code 0 (non-blocking)
- [ ] All CRITICAL matches reviewed
- [ ] Security agent routed for CRITICAL findings
- [ ] HIGH matches evaluated for review need
- [ ] Output captured in session log if security-relevant

---

## Related Documents

- [Infrastructure File Patterns](../../security/infrastructure-file-patterns.md)
- [Security Agent Capabilities](../../security/static-analysis-checklist.md)
- [Orchestrator Routing Algorithm](../../../docs/orchestrator-routing-algorithm.md)
