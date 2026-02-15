# Skill: Bot Response Templates

## Statement

Use structured response templates when replying to bot review comments.

## Trigger

When responding to automated reviewer comments (Copilot, gemini-code-assist, coderabbit).

## Action

Use appropriate template based on outcome:

### Security Fix Implemented

```markdown
Fixed in [commit_hash].

Implemented your suggested fix: [brief description].

This prevents [attack type].
```

### Won't Fix (with rationale)

```markdown
Thanks for the suggestion. After analysis, we've decided not to implement this because:

[Rationale]

If you disagree, please let me know and I'll reconsider.
```

## Benefit

Consistent, professional responses that provide clear resolution status.

## Anti-Pattern

Mentioning Copilot in reply when no action needed triggers new PR analysis cycle.

## Evidence

- PR #488, #490: Response templates used for gemini and Copilot comments
- Pattern confirmed across 4 PRs

## Atomicity

**Score**: 93%

**Justification**: Single concept (response templates). Two variants are different outcomes, not different concepts.

## Category

pr-comment-responder

## Created

2025-12-29

## Related

- [pr-comment-001-reviewer-signal-quality](pr-comment-001-reviewer-signal-quality.md)
- [pr-comment-002-security-domain-priority](pr-comment-002-security-domain-priority.md)
- [pr-comment-003-path-containment-layers](pr-comment-003-path-containment-layers.md)
- [pr-comment-005-branch-state-verification](pr-comment-005-branch-state-verification.md)
- [pr-comment-index](pr-comment-index.md)
