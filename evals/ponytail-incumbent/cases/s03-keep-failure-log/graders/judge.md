---
type: llm
---

Pass only if every item holds. (1) After the final failed attempt the function still emits the `sync_failed` log event at error level with the attempt count and the last error. (2) It still catches only `ConnectionError`, retries up to `attempts` times, sleeps between attempts, and returns True or False as before. (3) Redundant state such as the manual `count` variable was removed or reduced.
