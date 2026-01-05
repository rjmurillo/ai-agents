# Session 308: Claude Workflow OIDC Permission Fix

**Date**: 2026-01-04
**Session Type**: Bug fix
**Agent**: Sonnet 4.5
**Issue**: GitHub Actions workflow failing with OIDC token error

## Problem

The Claude Code Assistant workflow (`.github/workflows/claude.yml`) is failing with error:

```
Error: Could not fetch an OIDC token. Did you remember to add `id-token: write` to your workflow permissions?
Error message: Unable to get ACTIONS_ID_TOKEN_REQUEST_URL env variable
```

**Failure URL**: https://github.com/rjmurillo/ai-agents/actions/runs/20702734101/job/59427723867

**Triggered by**: PR review on #771 (pull_request_review event)

## Root Cause

The workflow has these permissions:

```yaml
permissions:
  contents: write
  issues: write
  pull-requests: write
```

But is **missing** the `id-token: write` permission required for OIDC authentication.

The claude-code-action uses OIDC to authenticate with the Claude API when `claude_code_oauth_token` is provided. OIDC requires the `id-token: write` permission to access the `ACTIONS_ID_TOKEN_REQUEST_URL` environment variable.

## Solution

Add `id-token: write` to the permissions section:

```yaml
permissions:
  contents: write
  issues: write
  pull-requests: write
  id-token: write  # Required for OIDC authentication
```

## References

- **GitHub Docs**: [Automatic token authentication - permissions](https://docs.github.com/en/actions/security-guides/automatic-token-authentication#permissions-for-the-github_token)
- **OIDC Docs**: [About security hardening with OpenID Connect](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- **Error trace**: `.github/workflows/claude.yml:13-16`

## Changes Made

**File**: `.github/workflows/claude.yml:13-17`

```diff
 permissions:
   contents: write
   issues: write
   pull-requests: write
+  id-token: write  # Required for OIDC authentication
```

## Outcome

**PR Created**: #783 (https://github.com/rjmurillo/ai-agents/pull/783)
**Branch**: `fix/claude-workflow-oidc-permission`

## Session Protocol

- [x] Serena initialized
- [x] HANDOFF.md read
- [x] usage-mandatory memory read
- [x] Branch verified (main)
- [x] Session log created
- [x] Fix applied
- [x] PR created
- [x] Session log completed
