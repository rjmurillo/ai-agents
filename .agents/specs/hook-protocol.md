# Hook Protocol Specification

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Continue normally |
| 1 | Fatal error | Log error, continue (hooks are non-blocking) |
| 2 | Guidance available | stderr contains model context to inject |
| 3 | Approval required | stderr contains what needs approval |

## stderr Protocol

Hooks communicate with the model via stderr. Content printed to stderr
is injected as system context. Users do not see stderr output.

### Format

Wrap output in XML-like tags for parseable boundaries:

`<memory-context>...</memory-context>` for recalled memories
`<memory-suggestion>...</memory-suggestion>` for fact capture suggestions
`<session-reflection>...</session-reflection>` for session summaries

### Truncation

Hooks SHOULD limit stderr output to 2000 tokens to avoid context bloat.
The harness MAY truncate at this boundary.

## Recommended Config Schema

```yaml
hooks:
  memory:
    auto_recall: true
    max_results: 3
    min_confidence: 0.3
  learning:
    governed_mode: true
    auto_capture: false
  reflection:
    run_on_session_end: true
    decay_enabled: true
```

## Reference Implementations

Two of the three memory scripts under `scripts/memory_enhancement/hooks/` ARE
registered, through thin wrapper hooks in `.claude/settings.json`, not by
direct path. The third has no wrapper and was retired.

- `scripts/memory_enhancement/hooks/user_prompt_submit_memory.py` (auto-recall):
  live. `.claude/hooks/UserPromptSubmit/invoke_memory_recall.py` is a thin
  invoker for it, registered under `UserPromptSubmit` in
  `.claude/settings.json`.
- `scripts/memory_enhancement/hooks/session_end_memory.py` (reflection): live.
  `.claude/hooks/SessionEnd/invoke_memory_reflection.py` is a thin invoker for
  it, registered under `SessionEnd` in `.claude/settings.json`.
- `scripts/memory_enhancement/hooks/post_tool_call_memory.py` (fact capture):
  **deleted by ADR-097**, which retired the `PostToolUseFailure` wrapper that
  was its only caller. Re-adding automatic fact capture means writing a new
  carrier and clearing `.claude/rules/tool-use-hook-bar.md` first.

So the memory system has automatic recall and reflection today; only
automatic fact capture is absent, and every memory that pipeline would have
written must instead come through explicit commands. Both live wrappers ship
under `.claude/hooks/`, not `scripts/memory_enhancement/hooks/` directly:
that directory does not travel with the plugin (see `plugin-self-containment.md`),
so the wrapper resolves the underlying package from `CLAUDE_PROJECT_DIR` and
fails open (silent no-op) on a consumer install where the script does not
exist.
