# Gemini Code Assist: Troubleshooting

## Reviews Not Appearing

Check these settings:

| Setting | Required Value |
|---------|----------------|
| `code_review.disable` | `false` |
| `pull_request_opened.code_review` | `true` |
| `include_drafts` | `true` (for draft PRs) |

Also verify:
- PR files not on excluded paths (`ignore_patterns`)
- Gemini app installed and authorized

## Too Many Comments

Solutions:

| Problem | Fix |
|---------|-----|
| Low-severity noise | Increase `comment_severity_threshold` to HIGH or CRITICAL |
| Overwhelming volume | Set `max_review_comments` to lower value (e.g., 10) |
| Reviewing wrong files | Refine `ignore_patterns` to exclude more files |

## Custom Rules Ignored

Verify:
- `styleguide.md` is in `.gemini/` folder (not root)
- Markdown syntax is valid
- Rules are specific and actionable (not vague)
- No group-level override (enterprise)

## Configuration Not Taking Effect

1. Check YAML syntax (use validator)
2. Verify file path is exactly `.gemini/config.yaml`
3. Push changes to default branch
4. Wait for Gemini to pick up changes (may take minutes)
