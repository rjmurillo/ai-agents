---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15002-fix-4942-readme-vscode-path.json
qaCommit: 2d043bd97834f8fe98fe31ffff5117cfae4e62ea
---

# QA Report: Issue #4942 - README VS Code Agent Path

## Summary

README.md line 217 listed `src/vs-code-agents/` as the VS Code agent location.
This disagreed with `docs/installation.md` line 96 which correctly states
`.github/agents/`. Fixed by updating README to `.github/agents/`.

## Test Results

- `tests/test_knowledge_surface_consistency.py`: 10/10 PASS
- New test `test_readme_and_installation_agree_on_vscode_agent_path`: PASS

## Verification

- Confirmed `src/vs-code-agents/` is a generator output (build/generate_agents.py)
- No installer deploys `src/vs-code-agents/` to consumers
- VS Code documentation confirms `.github/agents/` as the agent path
- `docs/installation.md` already states `.github/agents/` correctly

## Retrospective

Documentation fix with regression test plus a pre-existing subprocess encoding fix on main. Low risk.
