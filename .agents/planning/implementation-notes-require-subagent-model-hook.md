# Implementation Notes: Require Sub-Agent Model Hook

## Scope

- Parse complete hook payloads through 2 MiB and deny larger payloads.
- Resolve project definitions from `CLAUDE_PROJECT_DIR` before payload `cwd`.
- Resolve namespaced definitions from active Claude and Copilot plugin roots.
- Enforce the policy in repository Claude sessions without a second Copilot
  execution.
- Regenerate Copilot hook and operational skill mirrors.

## Security Flagging

**Status**: Security-relevant changes detected

**Triggered By**: Input handling and file-system definition lookup

**PIV Required**: Yes

**Justification**: Hook JSON and sub-agent names select fixed definition search
paths under project, user, and active plugin roots.

### Threat Review

- **Attack surface**: Hook JSON, `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, and
  `COPILOT_PLUGIN_ROOT`.
- **Threat actor**: Prompt-injected tool input can choose the sub-agent name and
  namespace, but cannot set the parent process environment.
- **Impact**: An unsafe namespace could escape a plugin search and incorrectly
  satisfy the model-pin policy. It cannot execute a definition file.
- **Controls**: Names reject glob metacharacters, separators, control
  characters, extra namespace separators, and `.` or `..` segments. Active
  plugin roots require a manifest name equal to the requested namespace.
  Payload reads stop at 2 MiB plus one byte and deny overflow.
- **CWE review**: CWE-22 and CWE-400 paths have regression coverage. No command
  construction, secret handling, or authorization boundary changed.

**Inline Verdict**: OK. No unmitigated medium-or-higher risk was identified.
Route the changed hook and generated shim to the security reviewer before
merge.

## Validation

- Focused hook and registration suite: 85 passed.
- Generator and dispatcher suite: 398 passed, 1 skipped.
- Runtime-contract and plugin-root suite: 36 passed.
- Shipped artifact and CLI E2E suite: 43 passed, 2 skipped.
- Plugin load smoke suite: 19 passed, 5 skipped.
- Scoped Ruff and mypy: passed.
- Plugin version validator: passed.
