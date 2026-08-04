# PreToolUse advisory-hook output envelope contract

A PreToolUse hook that wants to inject advisory context (not block) MUST emit the
`hookSpecificOutput` / `additionalContext` envelope. Using the top-level
`decision` field for advisories is invalid and the advisory is silently dropped.

## The contract

Advisory (non-blocking) output:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<advisory text>"}}
```

Blocking output uses the top-level `decision` field, which accepts only
`approve` or `block`:

```json
{"decision": "block", "reason": "<why>"}
```

## The trap (do not repeat)

`{"decision": "allow", "reason": ...}` is INVALID. `allow` / `deny` / `ask` are
not valid top-level `decision` values; they belong under
`hookSpecificOutput.permissionDecision`, a different field. When a hook emitted
`decision: allow`, the runtime schema check rejected the whole output with
`Hook JSON output validation failed: (root): Invalid input`, and the advisory
never reached the model. The error surfaced twice because the hook was
registered in both `.claude/settings.json` and the `project-toolkit` plugin, so
both copies ran and both emitted the bad JSON.

Two advisory hooks carried this defect and were fixed to the envelope above:

- `.claude/hooks/PreToolUse/invoke_correction_applier.py` (Self-Improving Agent
  correction memories)
- `.claude/hooks/PreToolUse/invoke_topical_memory_injection.py` (topical memory
  injection)

Impact of the bug: correction memories and topical memories were dropped before
reaching the model for roughly a week (regressions introduced 2026-05-29 in
#1763 and 2026-05-31 in #2005).

## Test the runtime contract, not a substring

The prior tests only checked stderr or substring-matched stdout, so the invalid
envelope passed green. This is the runtime-contract-not-tested anti-pattern. The
fix added stdout-JSON regression guards that parse the emitted JSON and assert
the envelope shape. When you touch an advisory hook, assert the parsed JSON
object shape, not a fragment of the text.

## Cross-harness note

Both hooks have generated Copilot CLI shims under `src/copilot-cli/hooks/`. After
editing the canonical `.claude/hooks/PreToolUse/*` copy, regenerate so the
hook-drift guard exits 0. The original fix also bumped
`.claude/.claude-plugin/plugin.json` (0.5.134 to 0.5.135); that step no longer
applies, since ADR-092 removed the `version` field from every manifest.

## Evidence

- Issue #2468 (root cause and fix description), closed by PR #2473.
- Fixed hooks: `.claude/hooks/PreToolUse/invoke_correction_applier.py`,
  `.claude/hooks/PreToolUse/invoke_topical_memory_injection.py`.
- Schema error observed: `PreToolUse:Bash hook error / Hook JSON output
  validation failed: (root): Invalid input`.
