# Hook Protocol Specification

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Continue normally |
| 1 | Fatal error | Log error, continue (hooks are non-blocking) |
| 2 | Guidance available | stderr contains model context to inject |
| 3 | Approval required | stderr contains what needs approval |

Exit code 2 is the PreToolUse and PostToolUse contract. It does not mean
"guidance available" on every event, and reading it that way ships hooks
that misbehave (issue #4011):

| Event | Channel that reaches the model | Meaning of exit 2 |
|-------|-------------------------------|-------------------|
| PreToolUse | stderr on exit 2 | Blocks the tool call |
| PostToolUse | stderr on exit 2 | Shows stderr to the model, tool already ran |
| UserPromptSubmit | stdout on exit 0 | Blocks the prompt and erases it |
| SessionEnd | none | Shows stderr to the user only |

So the recall hook writes to stdout and exits 0. The reflection hook exits 0
because the user-visible summary is all it produces: it scores every memory and
writes nothing, since a session that ends must not leave the working tree dirty.

## stderr Protocol

Hooks on PreToolUse and PostToolUse communicate with the model via stderr.
Content printed to stderr is injected as system context. Users do not see
stderr output. UserPromptSubmit uses stdout instead, per the table above.

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

Each is registered in `.claude/settings.json` through an invoker under
`.claude/hooks/<Event>/`. The invokers fail open when `scripts/` is absent,
so the hooks are dogfood-only: `scripts/memory_enhancement/` sits outside
every plugin root and does not travel to a consumer install.

| Implementation | Event | Invoker |
|----------------|-------|---------|
| `scripts/memory_enhancement/hooks/user_prompt_submit_memory.py` (auto-recall) | UserPromptSubmit | `.claude/hooks/UserPromptSubmit/invoke_memory_recall.py` |
| `scripts/memory_enhancement/hooks/post_tool_call_memory.py` (fact capture) | PostToolUse | `.claude/hooks/PostToolUse/invoke_memory_capture.py` |
| `scripts/memory_enhancement/hooks/session_end_memory.py` (reflection) | SessionEnd | `.claude/hooks/SessionEnd/invoke_memory_reflection.py` |
