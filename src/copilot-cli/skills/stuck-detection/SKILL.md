---
name: stuck-detection
version: 1.3.0
description: >-
  Detect agent loops (repeated topics or repeated tool failures) and emit a
  self-reflection nudge. Use as an orchestrator guard against token-burning
  loops. Use when you say "check stuck loop", "detect repetition", "agent
  looping", "check failure loop", or "reset stuck history". Do NOT use
  for semantic similarity checks or multi-turn intent tracking; use a richer
  evaluation tool for those.
license: MIT
metadata:
  routing:
    role: conditional-adjunct
    invoker: ai-agents-debugging-playbook
    trigger: in the ai-agents repository, ai-agents-debugging-playbook triggers stuck-detection after three read-only commands find no cause
    user-facing: false
---

# Stuck Detection Guard

Detect when an agent is repeating the same topics across turns, or retrying the
same failing command or edit, and surface a self-reflection nudge so the
orchestrator can break the loop. Lightweight, deterministic, no external
services, no model calls.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `check stuck loop` | Score current response against recent history |
| `detect repetition` | Flag repeating topic signatures |
| `agent looping` | Emit a loop-breaking nudge |
| `check failure loop` | Score recent tool events for a failure loop |
| `reset stuck history` | Clear history after a confirmed topic change |

## Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Agent re-states the same status every turn | Topic signature unchanged across turns | Inject the `nudge` payload before the next turn |
| False positive after a real topic change | Stale history kept after the user redirected | Run `reset` to clear history |
| Stuck never triggers despite obvious repetition | Responses below `MIN_TEXT_LENGTH` (50 chars) | Lower threshold or pass full response text |
| Unrelated turns flagged as stuck | Generic vocabulary inflates Jaccard score | Raise `DEFAULT_SIMILARITY_THRESHOLD` toward 0.75 |
| Same command fails again and again | Retrying without a new hypothesis | Run `check-failures`; on `stuck`, inject its `nudge` |
| A file keeps being edited, the same test still fails | Edit churn: each edit leaves the failure unchanged | Run `check-failures`; the `edit-churn` signal names the file |

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

### Failure loops (`check-failures`)

Stateless. The caller passes the recent tool events; nothing is stored. The
two signals are adapted from TokenEconomizer's failure-loop guard
(<https://github.com/microsoft/TokenEconomizer>). Unlike that guard, this one
runs in no hook, calls no judge model, and never stops a turn.

1. **Fingerprint.** Each failure reduces to its tool plus the first non-blank
   error line, lowercased, with digit runs replaced by `N` and hex runs of 7 or
   more characters by `H`. The same failure at another line number still
   matches.
2. **failure-repeat.** A fingerprint seen `--repeat` times (default 3) in the
   last `--window` events (default 20) trips the signal.
3. **edit-churn.** The first failure after a successful edit is that edit's
   outcome. A file whose `--churn` edits (default 3) share one outcome trips
   the signal. A success from a tool that failed earlier in the window (a
   check that now passes) resets the churn state. Reads and searches do not.

Event input is a JSON array. Each event needs `tool` (string) and `ok`
(boolean). `error` (string) is read for failures. `target` (string) names the
file an edit tool (`Edit`, `Write`, `MultiEdit`, `str_replace`, `create`,
`apply_patch`, `NotebookEdit`) changed; an edit without `target` is not
counted as an edit. Unknown keys are ignored. At most 10,000 events.

```json
[
  {"tool": "Edit", "ok": true, "target": "src/app.py"},
  {"tool": "Bash", "ok": false, "error": "FAILED tests/test_app.py::test_x"}
]
```

## Process

1. Run `python3 .claude/skills/stuck-detection/stuck_detection.py check "<text>"`
2. If the JSON result has `"stuck": true`, inject the `nudge` field into the
   orchestrator's next system prompt so the model self-corrects on its next
   turn. The `nudge` is internal control text wrapped in `<stuck-detection>`
   tags. Do not render it directly to the end user.
3. After a confirmed topic change, call `reset` to clear stale history.
4. For tool-failure loops, write the recent tool calls as events and run
   `check-failures`. On `"stuck": true`, inject its `nudge` the same way.

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

# Check recent tool events for a failure loop (file or stdin)
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/stuck-detection"
python3 "$SCRIPTS_DIR/stuck_detection.py" check-failures --events events.json
python3 "$SCRIPTS_DIR/stuck_detection.py" check-failures --repeat 4 < events.json
```

`check-failures` exits 0 with JSON on stdout whether or not it finds a loop.
It exits 2 with a `stuck-detection:` message on stderr and nothing on stdout
when the input is not valid JSON, does not match the event shape, the file
cannot be read, or a threshold is below 2.

### Output

```json
{
  "stuck": true,
  "signature": "deploy,error,pipeline,retry,timeout",
  "similar_count": 3,
  "nudge": "<stuck-detection>\nSELF-REFLECTION: Loop detected.\n..."
}
```

`check-failures` output:

```json
{
  "stuck": true,
  "events_checked": 9,
  "signals": [
    {"signal": "failure-repeat", "fingerprint": "bash|failed tests/test_app.py::test_x", "count": 3},
    {"signal": "edit-churn", "target": "src/app.py", "fingerprint": "bash|failed tests/test_app.py::test_x", "count": 3}
  ],
  "nudge": "<stuck-detection>\nSELF-REFLECTION: Failure loop detected.\n..."
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
| `DEFAULT_FAILURE_REPEAT` | 3 | Same-fingerprint failures to trip `failure-repeat` (`--repeat`) |
| `DEFAULT_EDIT_CHURN` | 3 | Same-outcome edits of one file to trip `edit-churn` (`--churn`) |
| `DEFAULT_FAILURE_WINDOW` | 20 | Most recent events `check-failures` reads (`--window`) |

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
- [ ] Three identical failures passed to `check-failures` return `"stuck": true` with a `failure-repeat` signal
- [ ] Malformed `check-failures` input exits 2 with nothing on stdout
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
