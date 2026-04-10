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

- `scripts/memory_enhancement/hooks/user_prompt_submit_memory.py` (auto-recall)
- `scripts/memory_enhancement/hooks/post_tool_call_memory.py` (fact capture)
- `scripts/memory_enhancement/hooks/session_end_memory.py` (reflection)
