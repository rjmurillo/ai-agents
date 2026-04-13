# Copilot CLI Setup for GitHub Actions

This guide explains how to configure GitHub Copilot CLI authentication for use
in GitHub Actions workflows.

## Prerequisites

- GitHub account with **Copilot subscription** (Individual, Business, or Enterprise)
- Repository admin access to configure secrets

## The Problem

GitHub Copilot CLI requires special authentication that differs from standard
GitHub CLI (`gh`) authentication:

- **Standard `GH_TOKEN`**: Works for GitHub API and `gh` commands
- **Copilot CLI**: Requires a token with explicit **"Copilot Requests"** permission

Without the correct token, Copilot CLI exits with code 1 and produces no output.

## Solution: Fine-Grained PAT with Copilot Requests Permission

### Step 1: Create a Fine-Grained Personal Access Token

1. Go to: <https://github.com/settings/personal-access-tokens/new>
2. Select **Fine-grained token** (not classic PAT)
3. Configure the token:
   - **Token name**: `COPILOT_GITHUB_TOKEN` (or descriptive name)
   - **Expiration**: Choose appropriate duration
   - **Repository access**: Select repositories or "All repositories"
4. Under **Account permissions**, enable:
   - **Copilot Requests**: `Read-only` ← **This is the critical permission**
5. Click **Generate token**
6. Copy the token immediately (you won't see it again)

### Step 2: Add Repository Secret

1. Go to your repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `COPILOT_GITHUB_TOKEN`
4. Value: Paste the token from Step 1
5. Click **Add secret**

### Step 3: Verify Workflow Configuration

The AI PR Quality Gate workflow should have:

```yaml
env:
  # GitHub CLI authentication (for gh commands)
  GH_TOKEN: ${{ secrets.BOT_PAT }}
  # Copilot CLI authentication (requires fine-grained PAT with "Copilot Requests")
  COPILOT_GITHUB_TOKEN: ${{ secrets.COPILOT_GITHUB_TOKEN }}
```

And action invocations should include:

```yaml
- uses: ./.github/actions/ai-review
  with:
    bot-pat: ${{ secrets.BOT_PAT }}
    copilot-token: ${{ secrets.COPILOT_GITHUB_TOKEN }}
```

## Token Precedence

The Copilot CLI checks environment variables in this order:

| Priority | Variable | Use Case |
|----------|----------|----------|
| 1 (Highest) | `COPILOT_GITHUB_TOKEN` | Dedicated Copilot auth (recommended) |
| 2 | `GH_TOKEN` | Shared GitHub CLI auth |
| 3 (Lowest) | `GITHUB_TOKEN` | CI/CD default token |

Using `COPILOT_GITHUB_TOKEN` avoids conflicts with other GitHub tooling.

## Troubleshooting

### Symptom: CLI exits with code 1, no output

**Diagnostics will show:**

```text
=== DIAGNOSTIC SUMMARY ===
Health Status: failed
Auth Status: authenticated as <user>

=== FAILURE ANALYSIS ===
The Copilot CLI produced no output (stdout or stderr).
This typically indicates:
- The GitHub account does not have Copilot access enabled
- The PAT token lacks Copilot permissions
```

**Solutions:**

1. **Check Copilot subscription**: The account owning the PAT must have an
   active Copilot subscription
2. **Verify token type**: Must be a **fine-grained PAT**, not classic PAT
3. **Check permission**: Token must have **"Copilot Requests: Read"** permission
4. **Regenerate if needed**: Create a new token following the steps above

### Symptom: Authentication works but review fails

Check that:

- The Copilot subscription is active (not expired)
- Organization policies allow Copilot CLI access
- Rate limits haven't been exceeded

### Viewing Diagnostics

The AI review action outputs detailed diagnostics:

- **copilot-health**: `healthy`, `degraded`, or `failed`
- **copilot-diagnostic**: Full health check results
- **auth-status**: Authentication details with token scopes

## Security Considerations

- **Token scope**: The "Copilot Requests" permission only allows sending
  prompts to Copilot; it doesn't grant repository access
- **Separate tokens**: Use different tokens for `BOT_PAT` (repo operations)
  and `COPILOT_GITHUB_TOKEN` (Copilot access)
- **Rotation**: Rotate tokens periodically and after any suspected compromise
- **Audit logs**: Monitor token usage in GitHub's security audit logs

## References

- [VeVarunSharma - Injecting AI Agents into CI/CD](https://dev.to/vevarunsharma/injecting-ai-agents-into-cicd-using-github-copilot-cli-in-github-actions-for-smart-failures-58m8)
- [DeepWiki - Copilot CLI Authentication Methods](https://deepwiki.com/github/copilot-cli/4.1-authentication-methods)
- [Elio Struyf - Custom Security Agent with GitHub Copilot](https://www.eliostruyf.com/custom-security-agent-github-copilot-actions/)
- [GitHub Community Discussion #167158](https://github.com/orgs/community/discussions/167158)
- [GitHub Docs - Using GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli)
