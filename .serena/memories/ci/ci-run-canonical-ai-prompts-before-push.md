# Run Canonical AI Prompts Before Push

**Atomicity**: 94%
**Category**: CI shift-left, AI quality gates

## Statement

Run matching canonical CI review prompts before the final push.

## Observation

[2026-08-09] [user]: PR #4587 spent a local pre-push cycle and a remote CI
cycle before the Architect review reported duplicate ratchet registrations.
The exact prompts were already committed under
`.github/prompts/pr-quality-gate-*.md` and could run locally against the final
diff.

When changed paths trigger the AI PR Quality Gate:

1. Build `CONTEXT_MODE: full` with the complete final diff.
2. Run every matching canonical prompt locally.
3. Fix supported Critical and High findings.
4. Record axis verdicts in the QA report.
5. Push only after deterministic gates and prompt gates pass.

Remote AI review is a backstop, not the first execution.

## Relations

- **related_to**: github/github-actions-local-testing-integration
- **related_to**: ci-infrastructure-ai-integration
- **related_to**: agent-behavior/error-recovery-obligations
