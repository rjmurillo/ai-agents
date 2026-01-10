# GitHub Keywords and PR Etiquette Guide

**Research Date**: 2026-01-10
**Source**: [GitHub Docs - Using keywords in issues and pull requests](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/using-keywords-in-issues-and-pull-requests)
**Context**: New developer onboarding for pull request workflow

---

## Table of Contents

1. [GitHub Issue Linking Keywords](#1-github-issue-linking-keywords)
2. [Conventional Commits for PR Titles](#2-conventional-commits-for-pr-titles)
3. [PR Template as Contract](#3-pr-template-as-contract)
4. [Review Etiquette](#4-review-etiquette)
5. [CI Etiquette](#5-ci-etiquette)
6. [Gold Standard Flow](#6-gold-standard-flow)
7. [Project Integration](#7-project-integration)

---

## 1. GitHub Issue Linking Keywords

### Supported Keywords

GitHub supports nine keywords to link pull requests with issues. When a PR containing these keywords merges, the linked issue closes automatically.

| Keyword Group | Variants |
|---------------|----------|
| **Close** | `close`, `closes`, `closed` |
| **Fix** | `fix`, `fixes`, `fixed` |
| **Resolve** | `resolve`, `resolves`, `resolved` |

### Syntax

```text
Keyword #issue-number
```

**Examples:**

```markdown
Closes #123
Fixes #456
Resolves #789
```

### Cross-Repository Linking

Link issues in different repositories using owner/repo syntax:

```text
Keyword owner/repository#issue-number
```

**Example:**

```markdown
Fixes rjmurillo/other-repo#100
```

### Case Sensitivity

GitHub keywords are case-insensitive. All variants work:

- `Closes #123`
- `closes #123`
- `CLOSES #123`

### Placement

Keywords work in:

- PR description body
- Commit messages (if PR description references the commit)
- PR title (not recommended, use description instead)

### Auto-Close Behavior

When a PR with linking keywords merges:

1. GitHub parses the PR description for keywords
2. Linked issues close automatically
3. The closing PR is referenced in the issue timeline
4. Works across repositories if you have write access to the target repo

---

## 2. Conventional Commits for PR Titles

### Format

```text
<type>(<scope>): <what changed>
```

### Types

| Type | Use Case | Example |
|------|----------|---------|
| `feat` | New functionality | `feat(auth): add refresh token rotation` |
| `fix` | Bug fix | `fix(api): handle null customer in OrderSummary` |
| `refactor` | Code restructuring | `refactor(payments): extract fee calculator` |
| `docs` | Documentation only | `docs(readme): add local setup steps` |
| `ci` | CI/CD changes | `ci: add ai-spec-validation workflow` |
| `build` | Build system | `build: bump dotnet sdk to 9.0.x` |
| `chore` | Maintenance | `chore: update dependencies` |
| `test` | Test additions | `test(api): add integration tests for auth` |
| `perf` | Performance | `perf(db): add index for user lookup` |
| `style` | Formatting | `style: fix linting errors` |

### Breaking Changes

Add `!` after the type/scope for breaking changes:

```text
feat(api)!: remove legacy v1 endpoints
```

Include a `BREAKING CHANGE:` footer in the PR description:

```markdown
## Summary

Removes deprecated v1 endpoints per deprecation notice.

BREAKING CHANGE: /api/v1/* endpoints no longer available. Use /api/v2/*.
```

### Scope Guidelines

- Keep scope lowercase
- Use the affected component, module, or domain
- Omit scope for cross-cutting changes

**Good scopes:**

```text
feat(auth): ...
fix(api): ...
refactor(payments): ...
docs(contributing): ...
```

**Avoid:**

```text
feat(AuthenticationService): ...  # Too specific
fix(bug): ...                     # Not a component
```

---

## 3. PR Template as Contract

The `.github/PULL_REQUEST_TEMPLATE.md` file defines the contract between author and reviewers. Fill it out as a mini design note.

### Section-by-Section Guide

#### Summary

**Purpose:** What + why in 2-4 bullets.

**Do:**

- State user-visible changes plainly
- Explain the problem being solved
- Keep implementation details out

**Example:**

```markdown
## Summary

- Add refresh token rotation to prevent token theft attacks
- Tokens now expire after 30 minutes of inactivity
- Old tokens are revoked when a new one is issued
```

#### Specification References

**Purpose:** Traceability for reviewers and automation.

**Required format:**

```markdown
| Type | Reference | Description |
|------|-----------|-------------|
| **Issue** | Closes #123 | Token expiration vulnerability |
| **Spec** | `.agents/planning/auth-token-rotation.md` | Design document |
```

**Rules by PR type:**

| PR Type | Spec Required? |
|---------|----------------|
| Feature (`feat:`) | Required |
| Bug fix (`fix:`) | Optional (link issue if exists) |
| Refactor (`refactor:`) | Optional |
| Docs (`docs:`) | Not required |
| CI/Build (`ci:`, `build:`) | Optional (link ADR if architecture impacted) |

#### Changes

**Purpose:** Help reviewers chunk the diff.

**Structure changes by file/component:**

```markdown
## Changes

- Add `TokenRotationService` for managing token lifecycle
- Update `AuthController` to call rotation on refresh
- Add Pester tests for rotation scenarios
- Update configuration schema for rotation settings
```

#### Type of Change

**Purpose:** Classify the PR for labeling and review routing.

Check one:

- [ ] Bug fix (non-breaking change fixing an issue)
- [x] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update
- [ ] Infrastructure/CI change
- [ ] Refactoring (no functional changes)

#### Testing

**Purpose:** Prove the change works.

If tests added:

```markdown
## Testing

- [x] Tests added/updated
- [x] Manual testing completed
- [ ] No testing required

**Test coverage:**

- `TokenRotationService.Tests.ps1` covers rotation logic
- Manual: verified token refresh in dev environment
```

If no tests:

```markdown
## Testing

- [ ] Tests added/updated
- [ ] Manual testing completed
- [x] No testing required (documentation only)
```

#### Agent Review

**Purpose:** Document security-sensitive reviews.

List files that require security review:

```markdown
### Security Review

- [x] Security agent reviewed infrastructure changes

**Files reviewed:**

- `.github/workflows/deploy.yml` (secrets handling)
- `scripts/Auth/New-TokenRotation.ps1` (token generation)
```

#### Checklist

**Purpose:** Self-review verification.

Complete before requesting review:

- [x] Code follows project style guidelines
- [x] Self-review completed
- [x] Comments added for complex logic
- [x] Documentation updated (if applicable)
- [x] No new warnings introduced

---

## 4. Review Etiquette

### Don't Waste Reviewer Time

| Rule | Reason |
|------|--------|
| Keep PRs small and single-purpose | Faster review, easier rollback |
| Split cleanup into separate PRs | Keeps changes focused |
| Respond with action + location | Saves reviewer lookup time |
| Don't resolve threads unilaterally | Team may prefer reviewer acknowledgment |

### Responding to Comments

**Format:**

```text
Updated [component] to [action]. See [commit/line reference].
```

**Examples:**

```markdown
Updated TokenService to validate expiry before rotation. See commit abc123.

Fixed null check in line 42 per suggestion. See AuthController.cs:42.
```

### Force Push Protocol

Avoid force pushing after review starts. If you must:

```markdown
⚠️ Rebased and squashed. Previous review comments may reference outdated code.
```

### Handling Rewrites

If significant changes needed:

```markdown
## Update Note

Rebased on main and rewrote the token storage approach based on review feedback.
Old comments on the storage mechanism may be outdated.
```

---

## 5. CI Etiquette

### Pre-Review Checklist

Do not request review while checks are red unless:

- PR is marked as Draft
- You explicitly state "feedback wanted, not merge-ready"

### Handling Flaky Tests

If a check is flaky:

1. Document the flake with prior occurrences
2. Link to tracking issue if exists
3. Re-run with explanation

**Example comment:**

```markdown
CI failure is known flaky test (see #456). Re-running.
```

### Never Hand-Wave Failures

Wrong:

```markdown
CI failed but it's probably fine.
```

Right:

```markdown
CI failure in `integration-tests` job:
- Root cause: Database timeout (see logs line 234)
- Action: Increased timeout in commit def456
- Tracking: #789 for persistent timeout issues
```

---

## 6. Gold Standard Flow

### New Developer Checklist

1. **Create PR as Draft** if seeking directional feedback early
2. **Ensure title matches Conventional Commits** format
3. **Fill template fully** (especially Spec References for `feat:` PRs)
4. **Self-review diff** before requesting review
5. **Run tests locally** before pushing
6. **Mark "Ready for review"** only when checks pass
7. **Request minimum necessary reviewers**

### Flow Diagram

```text
┌─────────────────┐
│ Create branch   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Make changes    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Self-review     │◄── Scan for debug code, config drift
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Run tests       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Push + Draft PR │◄── Optional: early feedback
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Fill template   │◄── Complete all sections
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Wait for CI     │
└────────┬────────┘
         │ ✓ All green
         ▼
┌─────────────────┐
│ Ready for review│
└─────────────────┘
```

---

## 7. Project Integration

### This Repository's Requirements

Per `.github/PULL_REQUEST_TEMPLATE.md` and project constraints:

| Requirement | Source |
|-------------|--------|
| Use PR template sections | `pr-template-requirement` memory |
| PowerShell only for scripts | ADR-005 |
| Use skills instead of raw `gh` | `usage-mandatory` memory |
| No logic in workflow YAML | ADR-006 |
| Session protocol compliance | SESSION-PROTOCOL.md |

### Specification Requirements by PR Type

| PR Type | Spec Required? | Guidance |
|---------|----------------|----------|
| Feature (`feat:`) | Required | Link issue, REQ-*, or spec in `.agents/planning/` |
| Bug fix (`fix:`) | Optional | Link issue if exists; explain root cause |
| Refactor (`refactor:`) | Optional | Explain rationale and scope |
| Documentation (`docs:`) | Not required | N/A |
| Infrastructure (`ci:`, `build:`) | Optional | Link ADR if architecture impacted |

### Keyword Usage in This Project

The PR template expects:

```markdown
| Type | Reference | Description |
|------|-----------|-------------|
| **Issue** | Closes #123 | Issue title here |
```

This integrates GitHub's auto-close keywords with the template's traceability requirements.

---

## Summary

**The core principle:** Don't fight the process. Make it effortless for reviewers and CI to say "yes."

**Key behaviors:**

1. Use linking keywords (`Closes #`, `Fixes #`) for automatic issue closure
2. Follow Conventional Commits in PR titles
3. Fill the PR template completely
4. Self-review before requesting review
5. Keep PRs small and focused
6. Respond to feedback with action and location
7. Wait for green CI before requesting review

---

## References

- [GitHub Docs: Using keywords in issues and pull requests](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/using-keywords-in-issues-and-pull-requests)
- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- Project: `.github/PULL_REQUEST_TEMPLATE.md`
- Project: `usage-mandatory` Serena memory
- Project: `pr-template-requirement` Serena memory
