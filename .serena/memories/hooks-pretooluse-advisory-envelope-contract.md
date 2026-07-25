# PreToolUse Advisory-Envelope Contract (#2468)

Scope: Claude Code only. Copilot CLI uses top-level `permissionDecision`,
`permissionDecisionReason`, `modifiedArgs`, and `additionalContext` fields.
Never copy this Claude envelope into a Copilot hook response.

## Contract

A PreToolUse hook that wants to surface advisory text to the model (not block/approve) MUST emit:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "<advisory>"}}
```

It MUST NOT emit a top-level `{"decision": "allow", "reason": ...}`. The top-level `decision` field accepts only `approve` or `block`. The values `allow`/`deny`/`ask` are valid only under `hookSpecificOutput.permissionDecision`, not top-level `decision`.

## Why (evidence)

Issue #2468: two advisory PreToolUse hooks (`.claude/hooks/PreToolUse/invoke_correction_applier.py`, `invoke_topical_memory_injection.py`) emitted `{"decision": "allow", ...}`. The schema check rejected the output with `Hook JSON output validation failed: (root): Invalid input`, so the advisory was dropped before reaching the model. Correction memories (Self-Improving Agent) and topical memories silently never surfaced. The bad form was introduced by #1763 (2026-05-29) and #2005 (2026-05-31) and appeared twice per Bash run because the hook is registered in both `.claude/settings.json` and the `project-toolkit` plugin.

## Apply when

Writing or reviewing any advisory (non-blocking) PreToolUse hook. Blocking guards correctly use top-level `{"decision": "block", ...}`; only the advisory path uses the `hookSpecificOutput.additionalContext` envelope.

Source: issue #2468 (CLOSED).
