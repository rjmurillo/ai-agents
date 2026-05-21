---
name: review-axes
version: 1.0.0
description: Canonical role-specific review-axis prompts for the /review command. Reference-only; not directly invocable. Holds analyst, architect, qa, security, devops, and roadmap axis prompts under references/{role}.md as the single source of truth.
license: MIT
---

# Review Axes (Reference-Only Skill)

This skill is a **reference repository**, not a directly invocable workflow. It exists to give the `/review` command a single, allowed source-of-truth location for its six canonical axis prompts. The skill lives here because `.claude/` only permits the `.claude-plugin`, `agents`, `commands`, `hooks`, `rules`, and `skills` subdirectories (per project layout policy); putting reference content inside a skill keeps the layout legal without conflating it with the `/review` workflow itself.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `read analyst axis` | Load `references/analyst.md` |
| `read architect axis` | Load `references/architect.md` |
| `read review axis` | Load axis prompt for a role |

## When to Use

Use these files when:

- Running the `/review` command (the command resolves them via "Path resolution" in its body).
- Updating one of the canonical axis prompts (this is the single source of truth).
- Mirroring axis content into a CI quality gate generator that needs the same prompt verbatim.

Do not invoke this skill directly to perform a review; use the `/review` command, which orchestrates the axes plus the three local-only chained skills.

## Files

| File | Purpose |
|------|---------|
| `references/analyst.md` | Code quality, impact, maintainability axis prompt |
| `references/architect.md` | Architecture and boundary axis prompt |
| `references/qa.md` | Test strategy and coverage axis prompt |
| `references/security.md` | OWASP and CWE security axis prompt |
| `references/devops.md` | CI/CD, deployment, ops axis prompt |
| `references/roadmap.md` | Strategic alignment and prioritization axis prompt |

## Bundling for vendored installs

The build pipeline mirrors `references/` into the bridged `/review` skill at `src/copilot-cli/skills/review/references/{role}.md` for Copilot CLI and similar plugin harnesses. The `/review` command body then resolves the axis prompt skill-relative in vendored installs, since the consumer repo has no `.claude/` mirror. See `templates/platforms/copilot-cli.yaml` (`artifacts.review-axes` stanza) and `build/scripts/build_all.py` (`_build_review_axes`).

## Process

1. Identify the role axis needed (analyst, architect, qa, security, devops, roadmap)
2. Read the corresponding prompt file from `references/{role}.md`
3. Use the prompt as system instruction for the matching agent type

This skill is reference-only and should not be invoked directly.

## Verification

- [ ] Axis prompt file exists at `references/{role}.md`
- [ ] Content matches the canonical source in `.claude/skills/review-axes/references/`

## Related Documents

- [/review command](../../commands/review.md)
- [Issue #2042](https://github.com/rjmurillo/ai-agents/issues/2042) - vendored install path resolution
