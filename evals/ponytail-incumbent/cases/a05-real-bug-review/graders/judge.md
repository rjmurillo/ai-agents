---
type: llm
---

Pass only if the reply identifies the SQL injection in `find_users_by_name` (user-controlled `name` interpolated into the query string) and says to use a parameterized query, for example `LIKE ?` with `f"%{name}%"` bound as a parameter. Flagging the missing test for the new function is acceptable but not required.
