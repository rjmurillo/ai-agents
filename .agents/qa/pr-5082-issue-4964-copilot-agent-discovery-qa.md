---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-4964.json
qaCommit: e08e58b372c1c5d4633e9c5f9b343314d7dd360a
---

# Issue #4964 QA Report

## Verdict

PASS. File-based fallback resolves Copilot CLI hosted-runner agent discovery.

## Test Results

| Check | Result |
|-------|--------|
| test_read_agent_tools_from_file_returns_analyst_tools | PASS |
| test_copilot_project_agent_tools_fallback_on_missing_event | PASS |
| test_copilot_project_agent_tools_primary_path | PASS |
| test_read_agent_tools_from_file_fails_on_missing_agent | PASS |
| test_copilot_analyst_runtime (local, primary path) | PASS |
| mypy type check | PASS |
| pre-push hooks | PASS |

## Acceptance Criteria

- [x] Reproduce project-agent discovery failure on hosted runners (run 31886004229)
- [x] Identify root cause: token-auth CLI skips enumeration event
- [x] Fix without weakening exact allowlist assertion
- [x] Keep token and plugin-load smoke controls green
- [x] Add positive, negative, and edge-case tests

## Risk Assessment

Low. Single file changed. No weakening of assertions. Fallback path reads
the same canonical source the CLI uses.
