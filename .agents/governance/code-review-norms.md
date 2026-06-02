# Code Review Norms

**Status**: Canonical Source for code review culture

This file is the single canonical source for the code review norms in this repository.
It is harness-neutral. Templates, skills, and agent prompts that need to cite review
culture link here; they do not restate the content.

These norms were inlined in `.github/PULL_REQUEST_TEMPLATE.md`'s `Notes for Reviewers`
block until they were extracted here so there is one authority instead of a copy that
drifts. The PR template now links to this file and keeps a render-safe summary that
points back here for authority.

## Norms

- **Assume competence and goodwill.** A "bad" PR usually means one party has
  information the other does not.
- **Explain _why_, not just _what_.** "This is wrong because..." beats "this is wrong."
- **Approve once the change improves overall code health.** Perfect is not the bar.
- **Target reply within ~1 business day.** If you cannot, leave a comment saying when
  you can.
- **Prefer "Approve with suggestions"** for minor issues, especially across timezones.
- **Authors: address every comment** by adopting, deferring (with a tracking issue), or
  pushing back with reasoning. Silence is not resolution.

## Comment Severity Prefixes

Authors triage by prefix. Reviewers prefix every comment so the author knows whether it
blocks merge.

| Prefix | Meaning |
|---|---|
| `Nit:` | Minor / style; do not block on it |
| `Optional:` | Worth considering; author may defer |
| `FYI:` | Future thought; no action needed |
| _(no prefix)_ | Must address before merge |

## Relationship to Other Sources

- The quality standards reviewers apply live in `.agents/governance/code-quality.md`.
- The review priorities ordering (security, correctness, exit codes, test coverage,
  style) lives in `.gemini/styleguide.md` under "Code Review Priorities."
- Security review is always-on and cannot be skipped; see
  `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`.

## References

- `.github/PULL_REQUEST_TEMPLATE.md`. Renders a summary of these norms and links here.
- `.agents/governance/code-quality.md`. The standards reviewers enforce.
- `.gemini/styleguide.md`. Routing index and review priorities.
