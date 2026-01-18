# Security Constraint: GitHub Actions SHA Pinning

**Status**: Enforced (BLOCKING)
**Added**: 2026-01-10 (Session 821)
**Source**: PROJECT-CONSTRAINTS.md, security-practices.md

## Requirement

ALL third-party GitHub Actions MUST be pinned to commit SHA, not version tags.

## Rationale

Version tags (e.g., `@v4`, `@v3`) are mutable references that can be moved to malicious commits by:
- Compromised action maintainer accounts
- Attackers who gain access to action repositories
- Malicious transfers of action ownership

SHA pinning ensures immutable references to reviewed code that cannot be silently replaced.

## Pattern

```yaml
# ✅ CORRECT: SHA with version comment for maintainability
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
uses: dorny/paths-filter@de90cc6fb38fc0963ad72b210f1f284cd68cea36 # v3

# ❌ WRONG: Version tag (mutable reference)
uses: actions/checkout@v4
uses: dorny/paths-filter@v3
```

## Enforcement Layers

1. **Pre-commit hook** (`.githooks/pre-commit`):
   - Scans staged workflow files for version tag patterns
   - Blocks commits with violations
   - Lines 706-777

2. **CI validation** (`.github/workflows/validate-generated-agents.yml`):
   - Runs `scripts/Validate-ActionSHAPinning.ps1 -CI`
   - Fails CI if violations found
   - Validates all workflows on every PR

3. **Validation script** (`scripts/Validate-ActionSHAPinning.ps1`):
   - Supports console, markdown, and JSON output formats
   - Can be run locally or in CI
   - Returns non-zero exit code with `-CI` flag if violations exist

## Finding SHA for Version Tag

```bash
gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'

# Example
gh api repos/actions/checkout/git/ref/tags/v4.2.2 --jq '.object.sha'
```

## Documentation References

- **Constraint**: .agents/governance/PROJECT-CONSTRAINTS.md#security-constraints
- **Guidance**: .agents/steering/security-practices.md#action-sha-pinning-blocking
- **Enforcement**: .githooks/pre-commit, .github/workflows/validate-generated-agents.yml
- **AGENTS.md**: "Always Do" section includes "Pin GitHub Actions to SHA"
- **CLAUDE.md**: Constraints table includes "SHA-pinned actions in workflows"

## Status

- All 26 workflows verified SHA-pinned (2026-01-10)
- Pre-commit hook active
- CI validation integrated
- Documentation updated

## Related

- Supply chain security best practices
- GitHub Security Hardening for Actions: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions
- OWASP Top 10: A06:2021 – Vulnerable and Outdated Components
