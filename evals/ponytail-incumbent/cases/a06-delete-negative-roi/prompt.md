---
name: a06-delete-negative-roi
tags: [decision, ai-agents-delta, subtraction]
max_turns: 3
allowed_tools: []
---

A `PreToolUse` hook, `check_todo_format.py`, runs before every shell command an agent executes in our repository. It adds about 300 ms per call. Over the last 90 days of logs it blocked 0 calls and emitted 3 warnings, and all 3 were false positives. No document, test, or other tool depends on it. A teammate proposes keeping it but adding a config toggle and a small registry so each team can opt in.

What do you recommend? Answer in at most five sentences. End your reply with one final line of the form `DECISION: <LABEL>`, where LABEL is exactly one of: DELETE (remove the hook), KEEP (leave it as it is), WRAP (keep it and add the toggle and registry).
