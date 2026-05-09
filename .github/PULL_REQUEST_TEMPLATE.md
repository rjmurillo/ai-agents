# Pull Request

<!--
Code review norms for this repo: assume competence and goodwill on both sides.
Authors: provide context, satisfy preconditions, state expectations.
Reviewers: explain *why*, reply within ~1 business day, prefer "approve with
suggestions" for minor issues. The "Notes for Reviewers" section near the
bottom of this template renders the full norms; see also
[.gemini/styleguide.md](../.gemini/styleguide.md).
-->

## Summary

<!--
What changed and *why*. The "why" is the part reviewers cannot get from the diff.
Keep this section short. Prefer many small PRs over one large one; isolate
rebases and pure refactors into their own commits or PRs.
-->

### What

<!-- 1-3 sentences on the change itself -->

### Why

<!-- The motivation: bug, requirement, ADR, incident, or constraint that drove this -->

## Specification References

<!-- Enable AI spec-to-implementation traceability -->
<!-- The ai-spec-validation workflow checks for these references -->

| Type | Reference | Description |
|------|-----------|-------------|
| **Issue** | Closes #<!-- issue number --> | <!-- Issue title --> |
| **Spec** | `.agents/planning/...` | <!-- Planning document --> |
| **Spec** | `.agents/specs/...` | <!-- Spec document (if applicable) --> |

### Spec Requirement Guidelines

| PR Type | Spec Required? | Guidance |
|---------|----------------|----------|
| **Feature** (`feat:`, `feat(scope):`) | Required | Link issue, REQ-*, or spec file in `.agents/planning/` |
| **Bug fix** (`fix:`, `fix(scope):`) | Optional | Link issue if exists; explain root cause if complex |
| **Refactor** (`refactor:`, `refactor(scope):`) | Optional | Explain rationale and scope in PR description |
| **Documentation** (`docs:`) | Not required | N/A |
| **Infrastructure** (`ci:`, `build:`, `chore:`) | Optional | Link ADR or design doc if architecture impacted |

<!--
Supported reference formats:
- Issues: "Closes #123", "Fixes #456", "Implements #789"
- Requirements: "REQ-001", "DESIGN-002", "TASK-003"
- Spec files: ".agents/specs/requirements/...", ".agents/planning/..."

For feature PRs: Create spec in .agents/planning/ before submitting if none exists.
For other PRs: Add references when traceability adds value.
-->

## Changes

<!-- Bulleted list of changes -->

-

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update
- [ ] Infrastructure/CI change
- [ ] Refactoring (no functional changes)

## Reviewer Expectations

**Review kind / scrutiny / urgency**: <!-- e.g., "design review, high scrutiny, blocks release" or "rubber stamp, low, no rush" -->

**Focus areas**: <!-- Files, sections, or trade-offs you want reviewers to weigh in on -->

<details>
<summary>Detailed options (expand if useful)</summary>

**Review kind**: full / design / targeted / rubber stamp
**Scrutiny**: high (security, data integrity, public API, governance) · standard · low (typo, doc tweak, dep bump)
**Urgency**: blocks release · soft target · no rush

</details>

## Testing

Deliverables in this PR:

- [ ] Tests added/updated
- [ ] Manual testing completed
- [ ] No testing required (documentation only)

## Agent Review

<!-- Check applicable boxes for agent-assisted development -->

### Security Review

> Required for: Authentication, authorization, CI/CD, git hooks, secrets, infrastructure

- [ ] No security-critical changes in this PR
- [ ] Security agent reviewed infrastructure changes
- [ ] Security agent reviewed authentication/authorization changes
- [ ] Security patterns applied (see `.agents/security/`)

**Files requiring security review:**

<!-- List security-critical files if any:
- .github/workflows/...
- .githooks/...
- **/Auth/**/...
-->

### Other Agent Reviews

- [ ] Architect reviewed design changes
- [ ] Critic validated implementation plan
- [ ] QA verified test coverage

## Author Pre-flight

<!--
Adapted from "Satisfy preconditions" in the team's code review norms.
Run these locally before requesting review so reviewers spend their time on
substance, not on catching what tooling already catches.
-->

- [ ] Builds locally (or N/A)
- [ ] Pre-PR validation passed (`python3 scripts/validation/pre_pr.py`; pass `--quick` to skip slow validations or `--skip-tests` for very fast iterations)
- [ ] Lint and formatting clean (scoped to changed files)
- [ ] Code follows project style guidelines ([.gemini/styleguide.md](../.gemini/styleguide.md))
- [ ] Self-review completed (read the diff as if you did not write it)
- [ ] Comments added only where the *why* is non-obvious
- [ ] Documentation updated (if applicable)
- [ ] No new warnings introduced

## Notes for Reviewers

<details>
<summary>Review norms (expand)</summary>

- **Assume competence and goodwill.** A "bad" PR usually means one party has information the other does not.
- **Explain *why*, not just *what*.** "This is wrong because..." beats "this is wrong."
- **Approve once the change improves overall code health.** Perfect is not the bar.
- **Target reply within ~1 business day.** If you cannot, leave a comment saying when you can.
- **Prefer "Approve with suggestions"** for minor issues, especially across timezones.
- **Authors: address every comment** by adopting, deferring (with a tracking issue), or pushing back with reasoning. Silence is not resolution.

**Comment severity prefixes** (so authors can triage):

| Prefix | Meaning |
|---|---|
| `Nit:` | Minor / style; do not block on it |
| `Optional:` | Worth considering; author may defer |
| `FYI:` | Future thought; no action needed |
| *(no prefix)* | Must address before merge |

</details>

## Related Issues

<!-- Link related issues: Fixes #123, Closes #456 -->

---

<!-- Optional: Add screenshots for UI changes -->
