# Gemini Code Assist: Best Practices & Anti-Patterns

## Enable Reviews When

- Team wants automated feedback
- Consistent style enforcement needed
- Security vulnerability detection desired

## Disable Summaries When

- PR titles/descriptions are sufficient
- Reducing comment noise is priority
- Team prefers human-written summaries

## Include Drafts When

- Early feedback is valuable
- Iterative review process preferred

## Exclude Drafts When

- Draft PRs are exploratory/incomplete
- Review noise should be minimized

## Configuration Anti-Patterns

**Don't**:
- Set `max_review_comments: 0` (use `code_review.disable: true` instead)
- Use `ignore_patterns` for temporary exclusions (use PR-level settings)
- Enable `have_fun` in professional repositories
- Disable memory without clear reason

## Style Guide Anti-Patterns

**Don't**:
- Copy-paste entire language style guides (link instead)
- Write style guides longer than actual code
- Contradict linter/formatter rules
- Include non-style content (architecture, deployment)

## References

- **Official Docs**: https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github
- **Glob Patterns**: https://code.visualstudio.com/docs/editor/glob-patterns
