---
type: llm
---

Pass only if the rewrite still cannot leave a truncated or partially written settings file when the process crashes mid-write: it writes to a temporary file and atomically replaces the target, and it does not leave the temporary file behind on failure. Keeping or dropping fsync is acceptable either way if the reply states the trade-off. A plain `path.write_text(...)` fails.
