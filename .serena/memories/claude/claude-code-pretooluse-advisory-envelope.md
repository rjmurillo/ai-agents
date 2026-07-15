# PreToolUse advisory hooks: use hookSpecificOutput.additionalContext

Issue #2468, session 2368, 2026-06-06.

## Hook output schema (Claude Code PreToolUse)

- Top-level `decision` accepts ONLY `approve` | `block`. Blocking guards use
  `{"decision": "block", "reason": ...}` (invoke_branch_protection_guard,
  invoke_branch_context_guard, invoke_false_completion_gate).
- `allow` | `deny` | `ask` are values of `hookSpecificOutput.permissionDecision`
  (setting permissionDecision also auto-approves/denies the tool).
- To surface ADVISORY context to the model WITHOUT a permission decision:
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<text>"}}`
- `{"decision": "allow", "reason": ...}` FAILS harness validation
  ("(root): Invalid input") and the output is DROPPED silently. The advisory
  never reaches the model. invoke_correction_applier.py and
  invoke_topical_memory_injection.py shipped this from 2026-05-29 to 2026-06-06.

## Test the runtime contract, not the side channel

Both hook tests checked `stderr` or substring-matched `stdout`, never parsed
stdout as JSON, so the invalid envelope passed green. Regression guard: parse
stdout JSON, assert `hookSpecificOutput.additionalContext`, assert no top-level
`decision` key. See `mem:feedback-self-referential-test-anti-pattern`.

## generate_hooks footgun (absolute repo_root)

`build/scripts/generate_hooks.generate_hooks(config_path, repo_root)` MUST take
an ABSOLUTE `repo_root`. A relative `.` crashes in `_handle_event_drop`
(`src.relative_to(script_source)`) and, on a second run, seeds case-variant
scratch dirs (`preToolUse/`, `sessionEnd/`, `__case_fix_*`) under
`src/copilot-cli/hooks/` that collide via `_ensure_exact_case_dir`. The drift
guard and CI `build_all.py` pass absolute paths. To regenerate one hook's shim:
call with an absolute root on a CLEAN tree; verify `git status` shows only the
intended `__<Matcher>_<hash>.py` shim. The shim embeds the canonical hook body
inline (`_original_main`), so editing `.claude/hooks/**` requires regenerating
the shim or the hook-drift guard blocks the push.
