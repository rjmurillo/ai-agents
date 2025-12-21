---
number: 196
title: "refactor: Decompose monolithic skills-*.md memories into atomic skill files"
state: OPEN
created_at: 12/20/2025 13:34:41
author: rjmurillo-bot
labels: ["documentation", "enhancement"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/196
---

# refactor: Decompose monolithic skills-*.md memories into atomic skill files

## Summary

The skillbook agent now generates atomic skill files (e.g., `skill-serena-001-symbolic-tools-first.md`) with an index file. However, several existing monolithic `skills-*.md` files remain that should be decomposed for better token efficiency and discoverability.

## Files to Decompose

| File | Size | Priority |
|------|------|----------|
| `skills-github-cli.md` | 18KB | P1 |
| `skills-ci-infrastructure.md` | 17KB | P1 |
| `skills-gemini-code-assist.md` | 12KB | P2 |
| `skills-jq-json-parsing.md` | 11KB | P2 |
| `pr-comment-responder-skills.md` | 11KB | P1 |
| `skills-validation.md` | 10KB | P2 |

## Target Pattern

Each monolithic file should become:
- Multiple `skill-{category}-NNN-{name}.md` files (one per skill)
- One `skill-{category}-index.md` file for quick reference

## Benefits

- **Token efficiency**: Only load relevant skills, not entire 18KB files
- **Discoverability**: Clear naming pattern for skill lookup
- **Atomicity**: Each skill independently referenceable

## Acceptance Criteria

- [ ] All skills-*.md files decomposed into atomic skill files
- [ ] Each skill has: trigger, action, benefit, atomicity score
- [ ] Index files created for each category
- [ ] Original monolithic files deleted
- [ ] No duplicate content

## Related

- skill-serena-* files (reference implementation)
- skill-cost-* files (reference implementation)

