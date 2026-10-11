# Copilot CLI Setup for GitHub Actions

This guide explains how to configure GitHub Copilot CLI authentication for the
Copilot legs of the CLI smoke (`.github/workflows/plugin-cli-smoke.yml`).

The `ai-review` action no longer calls Copilot. It reviews with Claude and reads
`ANTHROPIC_API_KEY` in the `agent-claude` environment (REQ-047, issue #6069).
The Copilot token is read only by the Copilot smoke legs, in `agent-copilot`.

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

1. Go to your repository → **Settings** → **Environments** → `agent-copilot`
2. Under **Environment secrets**, click **Add environment secret**
3. Name: `COPILOT_GITHUB_TOKEN`
4. Value: Paste the token from Step 1
5. Click **Add secret**

### Step 3: Verify Workflow Configuration

Only the Copilot smoke steps read the token, and the job declares the
`agent-copilot` environment:

```yaml
environment: agent-${{ matrix.cli }}
...
env:
  COPILOT_GITHUB_TOKEN: ${{ secrets.COPILOT_GITHUB_TOKEN }}
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

### Symptom: a Copilot smoke leg fails or reports no tests ran

Check that:

- The account owning the PAT has an active Copilot subscription
- The token is a **fine-grained PAT** with **"Copilot Requests: Read"**
- The `agent-copilot` environment approval was granted
- Organization policies allow Copilot CLI access
- Rate limits and the monthly quota have not been exceeded

`scripts/validation/assert_smoke_ran.py` fails the leg when the smoke was
skipped, so a missing token surfaces as a red run.

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
