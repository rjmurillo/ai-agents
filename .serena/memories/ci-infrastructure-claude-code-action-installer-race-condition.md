# CI Infrastructure: claude-code-action Installer Race Condition

**Date**: 2026-01-05
**Importance**: HIGH
**Category**: CI/CD, Debugging, GitHub Actions

## Issue

The `anthropics/claude-code-action` workflow failed with "another process is currently installing Claude" error after 3 installation attempts.

## Root Cause

Race condition in claude-code-action v1.0.27 installer logic:

1. Installation uses `timeout 120` to limit each attempt to 120 seconds
2. The `timeout` command kills the shell process but NOT the Claude Code installer process
3. Installer continues running in background after timeout
4. Installer creates a lock file to prevent concurrent installations
5. Subsequent retry attempts detect the lock and fail immediately

## Symptoms

```
✘ Installation failed

Could not install - another process is currently installing Claude. Please try
again in a moment.

Try running with --force to override checks
```

Failed after 3 installation attempts with the same error.

## Timeline Example

From workflow run 20737935687:
- 04:22:58 - Installation attempt 1 starts
- 04:23:02 - Installer begins setup
- 04:24:58 - 120-second timeout kills shell command (installer continues)
- 04:24:58 - Background: "Installing Claude Code native build 2.0.74..."
- 04:25:03 - Attempt 2 starts
- 04:25:17 - Attempt 2 fails: "another process is currently installing Claude"
- 04:25:22 - Attempt 3 starts
- 04:25:35 - Attempt 3 fails: same error

## Resolution

**Upgrade to claude-code-action v1.0.28 or later**

v1.0.28 (released 2026-01-05) includes:
> "Bug fixes for orphaned installer processes and SDK path handling"

### Implementation

Update workflow YAML:

```yaml
# Change from:
- uses: anthropics/claude-code-action@7145c3e0510bcdbdd29f67cc4a8c1958f1acfa2f  # v1.0.27

# To:
- uses: anthropics/claude-code-action@c9ec2b02b40ac0444c6716e51d5e19ef2e0b8d00  # v1.0.28
```

## Alternative Workarounds (if upgrade not possible)

### Option A: Pre-Install Claude Code

```yaml
- name: Pre-install Claude Code
  shell: bash
  run: |
    timeout 300 bash -c "curl -fsSL https://claude.ai/install.sh | bash -s -- 2.0.74"
    claude --version

- uses: anthropics/claude-code-action@v1.0.27
  with:
    path_to_claude_code_executable: /home/runner/.claude/bin/claude
```

### Option B: Increase Timeout and Wait Between Retries

This would require forking the action and modifying the installer script:
- Increase timeout from 120s to 300s
- Add 30-60s wait between retry attempts
- Add lock file cleanup between retries

## Prevention

- Keep claude-code-action updated to latest version
- Monitor for installer-related issues in release notes
- Consider pre-installation if installation reliability is critical

## Related Issues

- Issue #804: Workflow failure that surfaced this issue
- Session 374: Investigation and resolution
- Commit 555f87c9: Fix implementation

## References

- Failed workflow: https://github.com/rjmurillo/ai-agents/actions/runs/20737935687
- v1.0.28 release: https://github.com/anthropics/claude-code-action/releases/tag/v1.0.28
- Session log: .agents/sessions/2026-01-05-session-374-issue-804-debug.md
