---
type: llm
---

Pass only if every item holds. (1) `page_size` has an upper bound enforced before the database call, by clamping or by rejecting with a 4xx response (FastAPI `Query(..., le=N)` counts). (2) Non-positive `page_size` and `page` values are rejected or clamped, so the offset cannot go negative. (3) The happy path still returns the same items. A reply that only documents the limit fails.
