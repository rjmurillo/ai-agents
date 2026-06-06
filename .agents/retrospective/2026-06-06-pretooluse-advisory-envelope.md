# Retrospective: PreToolUse advisory hooks emitted invalid decision:allow JSON

> **Date**: 2026-06-06
> **Severity**: Medium (developer-facing; advisory dropped, terminal error surfaced)
> **Issue**: #2468
> **No blame**: This retro critiques artifacts and process, not individuals.

## Summary

Two advisory `PreToolUse` hooks emitted `{"decision": "allow", "reason": ...}`.
`"allow"` is not a valid value for a PreToolUse hook's top-level `decision`
field (it accepts only `approve`/`block`). The values `allow`/`deny`/`ask`
belong under `hookSpecificOutput.permissionDecision`. The harness schema check
rejected the output, so the advisory was dropped before reaching the model and
a `Hook JSON output validation failed: (root): Invalid input` error surfaced on
every Bash command.

## Impact

| Area | Severity | Description |
|------|----------|-------------|
| Self-Improving Agent | Medium | Correction memories never surfaced; the Apply step was a silent no-op |
| Topical memory injection | Medium | Topical memories never surfaced on Write/Edit |
| Developer experience | Medium | A hook error printed on every Bash command for ~8 days |

## Failure modes

- **Silent failure at an integration point** (`.claude/rules/release-it.md`,
  "Silent API Migration Failures"). The hook loaded and ran without raising; the
  only signal was the harness validation error. The advisory side effect never
  fired and nothing asserted that it did.
- **Runtime contract not tested** (`.claude/rules/generated-artifacts.md`;
  `.claude/rules/canonical-source-mirror.md`, self-referential test anti-pattern).
  Both hook tests asserted the wrong surface: `test_invoke_correction_applier`
  checked `stderr`, `test_topical_memory_injection` substring-matched `stdout`.
  Neither parsed stdout as JSON or asserted the hook protocol envelope, so the
  invalid `{"decision": "allow"}` output passed green.

## Evidence

- Root cause code: `.claude/hooks/PreToolUse/invoke_correction_applier.py` (was line 224),
  `.claude/hooks/PreToolUse/invoke_topical_memory_injection.py` (was line 268).
- Introduced: #1763 (2026-05-29), #2005 (2026-05-31).
- Sibling blocking guards use the valid `{"decision": "block"}` form, which is
  why only the two advisory hooks were affected.
- Fix commits: `6d9b96be8` (hooks + shims + plugin bump), `ee35428b3` (tests).

## Remediation

- Both hooks now emit `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "additionalContext": "<advisory>"}}`. Verified live: the running harness
  injected the advisory as `additionalContext` with no error.
- Added stdout-JSON regression guards to both tests: parse stdout, assert the
  `additionalContext` envelope, assert no top-level `decision` key.
- Regenerated the `src/copilot-cli/hooks/` shims; the hook-drift guard exits 0.
- Bumped `plugin.json` 0.5.134 to 0.5.135.

## Follow-up

- Republish the `project-toolkit` plugin from this fix so consumer cache copies
  are durably fixed (the active local cache was patched as a stopgap only).
- Consider a guard or lint that flags `decision: allow|deny|ask` in any
  PreToolUse hook, since those values are only valid under `permissionDecision`.
