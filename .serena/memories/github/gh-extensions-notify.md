# GitHub Extension: gh-notify (meiji163/gh-notify)

## Skill-Ext-Notify-001: List Notifications (Static Mode)

**Statement**: Use `gh notify -s` for static (non-interactive) notification listing; combine with `-n`, `-f`, `-e` for filtering.

**Agent Compatibility**: YES - Use `-s` flag for static output.

```bash
# List unread notifications (static mode - REQUIRED for agents)
gh notify -s

# Limit to N notifications
gh notify -s -n 20

# Show all (read + unread)
gh notify -s -a

# Only participating/mentioned
gh notify -s -p

# Filter by regex pattern
gh notify -s -f "security"
gh notify -s -f "dependabot"

# Exclude by regex pattern
gh notify -s -e "bot"
gh notify -s -e "renovate"

# Combine filters
gh notify -s -n 50 -f "ai-agents" -e "dependabot"
```

**Output Format**: `unread_symbol time repo type number reason title`

## Skill-Ext-Notify-002: Mark Notifications as Read

**Statement**: Use `gh notify -r` to mark all notifications as read in batch.

```bash
# Mark ALL notifications as read
gh notify -r
```

## Skill-Ext-Notify-003: Subscribe/Unsubscribe to Issues

**Statement**: Use `gh notify -u URL` to toggle subscription on specific issues/PRs.

```bash
# Subscribe/unsubscribe (toggle)
gh notify -u https://github.com/owner/repo/issues/123
```

## Related

- [gh-extensions-anti-patterns](gh-extensions-anti-patterns.md)
- [gh-extensions-combine-prs](gh-extensions-combine-prs.md)
- [gh-extensions-grep](gh-extensions-grep.md)
- [gh-extensions-hook](gh-extensions-hook.md)
- [gh-extensions-maintenance](gh-extensions-maintenance.md)
