# Skill-PR-250: Bot Mention Side Effects

**Statement**: Avoid mentioning bots in replies to prevent unwanted triggers.

**Context**: PR comment acknowledgment and response workflows

**Evidence**: Session 87 - Mentioning @copilot triggered new PR analysis (costs premium requests); @coderabbitai triggers re-review

**Atomicity**: 95% | **Impact**: 6/10

## Anti-Pattern

```markdown
Thanks @copilot for catching this!
<!-- Triggers new premium request -->

@coderabbitai acknowledged
<!-- Triggers re-review cycle -->
```

## Pattern

```markdown
# Use reactions instead of mentions for acknowledgment
gh api --method POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions \
  -f content='+1'

# Or text acknowledgment WITHOUT bot mention
"Acknowledged. Fixed in abc1234."
```

## Side Effects by Bot

| Bot | Mention Trigger | Cost |
|-----|----------------|------|
| @copilot | New PR analysis | Premium request quota |
| @coderabbitai | Re-review | Re-analysis cycle |

## When to Mention

Only mention bots when you NEED their response:
- Request clarification on unclear comment
- Ask for re-analysis after major refactor
- Request verification of fix

**Default**: Use reactions for acknowledgment.

## Related

- **USES**: pr-review-acknowledgment.md (reaction-based acknowledgment)
- **PREVENTS**: Unnecessary bot re-analysis cycles
