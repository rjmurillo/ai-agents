# Memory: CI Runner Preference

**Entity**: CI-Runner-Preference
**Type**: Best Practice
**Date**: 2025-12-16
**Source**: PR Feedback (rjmurillo/ai-agents#PR-remediation)

## Observations

1. **Use `ubuntu-latest` (or `linux-latest`) runners for GitHub Actions workflows** instead of `windows-latest`
   - Linux runners are **MUCH faster** than Windows runners in GitHub Actions
   - Significant performance improvement for CI/CD pipelines

2. **Exception**: Only use `windows-latest` when:
   - PowerShell Desktop (5.1) is required
   - Windows-specific features are needed
   - Testing Windows-only scenarios

3. **PowerShell Core (`pwsh`) compatibility**:
   - PowerShell Core runs on Linux runners
   - Should be preferred over PowerShell Desktop
   - Cross-platform scripts work identically

## Application

- All new GitHub Actions workflows should default to `ubuntu-latest`
- Review existing workflows to migrate from `windows-latest` to `ubuntu-latest`
- Document Windows-specific requirements when `windows-latest` is necessary

## Evidence

- `.github/workflows/validate-paths.yml`: Changed from `windows-latest` to `ubuntu-latest` per feedback
- PowerShell validation scripts run successfully on Linux runners

## Related

- GitHub Actions runner performance: https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners
- PowerShell Core cross-platform documentation
