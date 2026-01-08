---
id: "48043714-1c1b-4921-94f9-43615ee350f3"
title: "Implement Multi-Layered Git Hook Enforcement"
assignee: ""
status: 0
createdAt: "1767767005328"
updatedAt: "1767767097103"
type: ticket
---

# Implement Multi-Layered Git Hook Enforcement

## Objective

Create post-checkout hook and extend pre-commit hook to enforce session initialization through multi-layered hook strategy with configuration support and error handling.

## Scope

**In Scope**:
- Create `file:.githooks/post-checkout` hook with session log detection and skill recommendation
- Extend `file:.githooks/pre-commit` hook with session log validation section
- Implement configuration loading with JSON validation and error handling
- Add jq availability check with fallback to defaults
- Implement bypass mechanism with `--no-verify` support
- Test hook execution with sample commits and checkouts

**Out of Scope**:
- Claude Code lifecycle hooks (platform-specific, separate implementation)
- Changes to existing pre-commit hook sections (markdown lint, PowerShell analysis, etc.)
- Configuration file creation (handled in separate ticket)

## Spec References

- **Tech Plan**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/23a7f44b-69e7-4399-a164-c8eedf67b455 (Component 7: Git Hooks)
- **Core Flows**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/15983562-81e6-4a00-bde0-eb5590be882a (Flow 1, Flow 5, Hook Enforcement Strategy)

## Acceptance Criteria

1. **post-checkout hook created**:
   - Detects branch checkout events
   - Checks if session log exists for current date (pattern: `.agents/sessions/YYYY-MM-DD-session-*.md`)
   - Loads configuration from .agents/.session-config.json with error handling
   - Validates JSON before parsing, logs warnings on failure, uses defaults
   - Checks jq availability, warns if not installed
   - Displays skill recommendation if no session log exists
   - Non-blocking (exit 0 always)

2. **pre-commit hook extended**:
   - New section added after line 894 (Session Log Validation)
   - Checks if session log exists for current date
   - Loads configuration with same error handling as post-checkout
   - Validates session log using Validate-SessionProtocol.ps1
   - Blocks commit (exit 1) if validation fails
   - Displays fix instructions and bypass option
   - Respects `--no-verify` bypass flag

3. **Configuration error handling**:
   - Checks jq availability before parsing JSON
   - Validates JSON syntax with `jq empty`
   - Validates boolean values (true/false only)
   - Logs warnings to stderr on configuration errors
   - Falls back to hardcoded defaults on any error

4. **Hook testing**:
   - Manual test: checkout branch without session log → see recommendation
   - Manual test: commit without session log → blocked with error
   - Manual test: commit with invalid session log → blocked with error
   - Manual test: commit with valid session log → proceeds
   - Manual test: commit with `--no-verify` → bypasses validation

## Dependencies

- **Ticket 1**: Validation module refactoring (provides validation functions used by pre-commit hook)
- **Ticket 3**: Orchestrator and phase scripts (hooks recommend running orchestrator)

## Implementation Notes

**Configuration Loading Pattern** (from Tech Plan):

```bash
# Load configuration with error handling
CONFIG_FILE=".agents/.session-config.json"
PROMPT_ON_CHECKOUT=true  # Default value

if [ -f "$CONFIG_FILE" ]; then
    if ! command -v jq &> /dev/null; then
        echo "WARNING: jq not found, using default configuration" >&2
    else
        if jq empty "$CONFIG_FILE" 2>/dev/null; then
            PROMPT_ON_CHECKOUT=$(jq -r '.session.promptOnCheckout // true' "$CONFIG_FILE" 2>/dev/null)
            if [ "$PROMPT_ON_CHECKOUT" != "true" ] && [ "$PROMPT_ON_CHECKOUT" != "false" ]; then
                echo "WARNING: Invalid promptOnCheckout value, using default (true)" >&2
                PROMPT_ON_CHECKOUT=true
            fi
        else
            echo "WARNING: Malformed JSON in $CONFIG_FILE, using default configuration" >&2
            PROMPT_ON_CHECKOUT=true
        fi
    fi
fi
```

**Security Considerations** (from Tech Plan):
- Use `-NoProfile` when invoking pwsh from hooks
- Quote all variables in bash
- Use `--` separator for git commands
- Follow existing security patterns from file:.githooks/pre-commit
