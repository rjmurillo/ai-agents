---
name: stuck-detection
version: 1.2.0
model: claude-haiku-4-5
description: >-
  Detect agent conversation loops via topic-signature similarity and emit a
  self-reflection nudge. Use as an orchestrator guard against repetitive
  responses and token-burning loops.
license: MIT
---

# Stuck Detection Guard

Detect when an agent is repeating the same topics across turns and surface a
self-reflection nudge so the orchestrator can break the loop. Lightweight,
deterministic, no external services.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `check stuck loop` | Score current response against recent history |
| `detect repetition` | Flag repeating topic signatures |
| `agent looping` | Emit a loop-breaking nudge |
| `reset stuck history` | Clear history after a confirmed topic change |

## Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Agent re-states the same status every turn | Topic signature unchanged across turns | Inject the `nudge` payload before the next turn |
| False positive after a real topic change | Stale history kept after the user redirected | Run `reset` to clear history |
| Stuck never triggers despite obvious repetition | Responses below `MIN_TEXT_LENGTH` (50 chars) | Lower threshold or pass full response text |
| Unrelated turns flagged as stuck | Generic vocabulary inflates Jaccard score | Raise `DEFAULT_SIMILARITY_THRESHOLD` toward 0.75 |

## When to Use

Use this skill when:

- Building an orchestrator that risks repeating tool calls or status updates
- A long-running session shows degraded variety in responses
- You want a cheap pre-flight guard before sending a response

Use a richer evaluation instead when:

- You need semantic similarity (this uses lexical Jaccard only)
- You need multi-turn intent tracking
- You need cross-session coherence checks

## How It Works

1. **Topic signature.** Strip stopwords, take the top N significant words by
   frequency, sort them, and join with commas. This is the response's signature.
2. **History.** Append each signature with a UTC timestamp to a JSON file.
   Keep only the most recent entries.
3. **Jaccard similarity.** Compare the current signature against the most
   recent K entries. Count how many exceed the similarity threshold.
4. **Trigger.** When K consecutive recent entries are similar, emit a nudge
   payload telling the orchestrator to ask the user a question or change topic.

## Process

1. Run `python3 .claude/skills/stuck-detection/stuck_detection.py check "<text>"`
2. If the JSON result has `"stuck": true`, inject the `nudge` field into the
   orchestrator's next system prompt so the model self-corrects on its next
   turn. The `nudge` is internal control text wrapped in `<stuck-detection>`
   tags. Do not render it directly to the end user.
3. After a confirmed topic change, call `reset` to clear stale history.

## Usage

```bash
# Check a response for stuck pattern (text via arg or stdin)
python3 .claude/skills/stuck-detection/stuck_detection.py check "your response text"
echo "your response" | python3 .claude/skills/stuck-detection/stuck_detection.py check

# Show current history state
python3 .claude/skills/stuck-detection/stuck_detection.py status

# Reset history after a topic change
python3 .claude/skills/stuck-detection/stuck_detection.py reset

# Extract signature only (debugging)
python3 .claude/skills/stuck-detection/stuck_detection.py extract "your text"
```

### Output

```json
{
  "stuck": true,
  "signature": "deploy,error,pipeline,retry,timeout",
  "similar_count": 3,
  "nudge": "<stuck-detection>\nSELF-REFLECTION: Loop detected.\n..."
}
```

## Configuration

Defaults are conservative. Override at the function call site or via constants
in `stuck_detection.py`:

| Constant | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_MAX_HISTORY` | 10 | Entries retained on disk |
| `DEFAULT_STUCK_THRESHOLD` | 3 | Consecutive similar turns to trigger |
| `DEFAULT_SIMILARITY_THRESHOLD` | 0.6 | Jaccard cutoff for "similar" |
| `MIN_TEXT_LENGTH` | 50 | Skip short responses |
| `SIGNATURE_SIZE` | 5 | Top words per signature |

### History Path

Resolution order:

1. `--history <path>` CLI flag
2. `STUCK_DETECTION_HISTORY` environment variable (full path)
3. `STUCK_DETECTION_SESSION` environment variable (per-session file under the
   XDG state dir, e.g. `history-<session>.json`); use this when running
   multiple concurrent sessions to prevent cross-session contamination
4. `$XDG_STATE_HOME/claude-stuck-detection/history.json`
5. `~/.local/state/claude-stuck-detection/history.json`

Paths are expanded and resolved before use. Avoid relative `..` segments in
`--history` or `STUCK_DETECTION_HISTORY` if you need the resolved location to
match the input.

## Verification

After integrating, confirm the following before relying on the guard:

- [ ] `python3 .claude/skills/stuck-detection/stuck_detection.py status` returns valid JSON with the configured `history_length`
- [ ] Three calls to `check` with the same long input return `"stuck": true` on the third call
- [ ] A call to `reset` zeroes `history_length` on the next `status` check
- [ ] The history file lives outside the repository working tree (XDG state dir or env-overridden path)
- [ ] Generated `nudge` text is forwarded into the orchestrator system prompt, not rendered to the end user
- [ ] Concurrent `check` calls never produce truncated JSON (atomic write via temp file + replace)
- [ ] A malformed history file (non-list, missing keys, non-string values) is treated as empty and not propagated to callers
- [ ] Tests in `tests/skills/stuck-detection/` pass under `uv run pytest`

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Calling `check` on every token | High overhead, noisy signatures | Call once per agent turn |
| Treating `stuck: false` as proof of progress | Lexical similarity misses semantic loops | Pair with task-completion checks |
| Hardcoding the history path in callers | Breaks portability across environments | Use the env var or CLI flag |
| Ignoring `reset` after topic changes | History stays polluted | Reset when the user redirects |

## Integration

Call from a hook or orchestrator wrapper. When `stuck` is true, prepend the
`nudge` to the system prompt for the next turn so the model self-corrects.

## Testing

```bash
uv run pytest tests/skills/stuck-detection/ -v
```
