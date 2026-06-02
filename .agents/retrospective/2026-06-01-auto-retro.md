# Retrospective: 2026-06-01

Session 1872. First fix for issue #2205: anchor Copilot CLI hook commands to the
plugin root.

## Session Context

### Work Items

- Diagnosed the failure: the generated `src/copilot-cli/hooks/hooks.json` invoked
  `python3 -u "./hooks/<event>/<script>.py"` with `cwd: "."`. Copilot CLI runs a
  hook with `cwd` set to the user's working directory, not the plugin install
  dir, so the relative path failed with "No such file or directory" (reported on
  Windows).
- Changed `_build_copilot_entry` to anchor to
  `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` (bash) and
  `$env:COPILOT_PLUGIN_ROOT` (powershell). Regenerated hooks.json, bumped
  `plugin.json`, added a regression test.

### Evidence

- Commit `0bfb90713` (the branch's first #2205 fix). PR #2206. Issue #2205.

## Impact

| Area | Severity | Note |
|------|----------|------|
| Copilot CLI hooks | High | Root cause (cwd resolution) correctly identified |
| Verification method | High | Env-var name unverified; the test asserted its own output |

## What Went Well

- Correct root-cause diagnosis. The working directory is the user dir, not the
  plugin root, so a relative hook path cannot resolve. The anchoring direction
  was right and is what the follow-up confirmed.

## What Could Improve

- The variable `COPILOT_PLUGIN_ROOT` was inferred by analogy to
  `CLAUDE_PLUGIN_ROOT`, not verified by running the CLI. It happened to be
  correct, but the method was unsound: the same step could have shipped a wrong
  name that no test would have caught.
- The regression test asserted the literal command string the generator emits. It
  pins the output to itself; it cannot detect a wrong variable or prove the path
  resolves at runtime.
- PowerShell received a bare `$env:COPILOT_PLUGIN_ROOT` with no fallback, an
  asymmetry with the bash branch.
- The fix was Copilot-only. The identical anchoring requirement on the Claude
  plugin (`.claude/hooks/hooks.json`) was not addressed.

## Key Learnings

- The anchoring direction was correct; the verification method was not. Pair a
  contract assumption with an empirical check before merge.
- See session 1873 (`2026-06-02-auto-retro.md`) for the empirical verification,
  the runtime-contract test, the both-plugin gate, and the forced e2e that close
  these gaps.

## Failure Patterns

- **FM #9 Confident-incorrectness recurrence** (`.agents/governance/FAILURE-MODES.md`):
  an undocumented env-var contract assumed from analogy, plus a self-referential
  test. Remediated in session 1873.
