# QA Report - ai-spec-validation workflow PR number handling

## Scope
- Workflow: .github/workflows/ai-spec-validation.yml
- Change: Add PR_NUMBER env, fallback gh pr view for manual runs, and pass PR number to ai-review/comment steps.

## Validation
- Reviewed YAML for context propagation on pull_request and workflow_dispatch triggers.
- Confirmed ai-review steps use env.PR_NUMBER and PR metadata fallback exists.
- No code/tests impacted beyond workflow configuration.

## Tests
- Not run (workflow-only change).

## Outcome
- QA review complete; no additional issues identified.
