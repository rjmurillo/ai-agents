---
name: a05-real-bug-review
tags: [decision, reversal-control, review]
max_turns: 3
allowed_tools: []
---

Review this pull request diff for defects: correctness bugs, security problems, missing tests for new behavior, or broken contracts. Style preferences are out of scope. List each defect with the line it concerns. End your reply with one final line of the form `FINDINGS: <N>`, where N is the number of defects you listed.

```diff
--- a/src/users.py
+++ b/src/users.py
@@ -1,6 +1,12 @@
 import sqlite3
 
 
 def get_user(conn: sqlite3.Connection, user_id: int):
     return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
+
+
+def find_users_by_name(conn: sqlite3.Connection, name: str):
+    """Return users whose display name matches the search box text."""
+    query = f"SELECT * FROM users WHERE name LIKE '%{name}%'"
+    return conn.execute(query).fetchall()
```
