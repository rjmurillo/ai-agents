# GitHub Extension: gh-hook (lucasmelin/gh-hook)

## Skill-Ext-Hook-001: List Webhooks

**Statement**: Use `gh hook list` to view repository webhooks.

**Note**: Requires admin access to the repository.

```bash
# List webhooks for current repo
gh hook list

# Target specific repo
gh hook list --repo owner/repo
```

## Skill-Ext-Hook-002: Create Webhook from File

**Statement**: Use `gh hook create --file` for non-interactive webhook creation from JSON.

```bash
# Create from JSON file
gh hook create --file webhook.json

# Target specific repo
gh hook create --file webhook.json --repo owner/repo
```

**JSON File Format**:

```json
{
  "active": true,
  "events": ["push", "pull_request", "issues"],
  "config": {
    "url": "https://example.com/webhook",
    "content_type": "json",
    "insecure_ssl": "0",
    "secret": "optional-webhook-secret"
  }
}
```

**Common Events**: push, pull_request, issues, issue_comment, create, delete, release, workflow_run

## Skill-Ext-Hook-003: Delete Webhook

**Statement**: Use `gh hook delete` to remove webhooks by ID.

```bash
# Delete webhook by ID
gh hook delete 12345678

# Target specific repo
gh hook delete 12345678 --repo owner/repo
```
