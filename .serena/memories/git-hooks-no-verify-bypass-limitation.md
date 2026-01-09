# Git Hooks: --no-verify Bypass Limitation

## Problem

Exit code 2 does NOT prevent `git commit --no-verify` from bypassing pre-commit hooks.

Git's `--no-verify` flag completely disables hook execution before any hook code runs, regardless of exit codes.

## Evidence

Tested with minimal hook that exits with code 2:

```bash
#!/bin/bash
echo "This hook exits with code 2"
exit 2
```

Results:
- `git commit -m "test"` → Hook runs, blocks commit (exit 2)
- `git commit -m "test" --no-verify` → Hook never runs, commit succeeds

**Conclusion**: `--no-verify` prevents hook execution entirely. Exit codes are never evaluated.

## Implications

**Git pre-commit hooks CANNOT enforce protocol compliance against willful bypass.**

Any agent (or developer) can bypass validation with `--no-verify` regardless of:
- Exit codes (1, 2, or any other value)
- Error messages
- Documentation warnings
- File lock checks

## Solution: Claude Hooks

Claude Code hooks are the ONLY enforcement mechanism that cannot be bypassed:

1. **SessionStart:compact** - Enforces protocol initialization before any work
2. **ToolCall** - Blocks bash/git commands when validation fails
3. **UserPromptSubmit** - Can enforce session log existence

Claude hooks execute at LLM level BEFORE commands reach bash/git, making them truly non-bypassable.

## Implementation Pattern

```bash
# SessionStart:compact hook
if ! ls .agents/sessions/$(date +%Y-%m-%d)-session-*.md 1>/dev/null 2>&1; then
  echo "ERROR: No session log found for today"
  echo "BLOCKING: Cannot proceed without session initialization"
  exit 1  # Blocks ALL further execution
fi
```

## Anti-Pattern

```bash
# Pre-commit hook (CAN BE BYPASSED)
if [ ! -f .agents/sessions/current-session.md ]; then
  echo "ERROR: No session log found"
  exit 2  # Agent can bypass with --no-verify
fi
```

## Related

- Session: 2026-01-09-session-01 (protocol violation aftermath)
- Retrospective: 2026-01-09-session-protocol-violation-analysis.md
- User directive: "let's remove the `--no-verify` as an option"
- Finding: Exit code 2 approach proven ineffective through testing

## References

- Git documentation: `--no-verify` flag bypasses all hooks unconditionally
- Claude Code: Hook system operates at LLM level, truly non-bypassable
- ADR-007: Memory-first architecture requires technical enforcement, not trust-based
