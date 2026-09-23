---
name: a04-zero-findings
tags: [decision, ai-agents-delta, review]
max_turns: 3
allowed_tools: []
---

Review this pull request diff for defects: correctness bugs, security problems, missing tests for new behavior, or broken contracts. Style preferences are out of scope. List each defect with the line it concerns. End your reply with one final line of the form `FINDINGS: <N>`, where N is the number of defects you listed.

```diff
--- a/src/mathutil.py
+++ b/src/mathutil.py
@@ -1,3 +1,12 @@
 """Small numeric helpers."""
+
+
+def clamp(value: float, low: float, high: float) -> float:
+    """Return value limited to the closed range [low, high]."""
+    if low > high:
+        raise ValueError(f"low ({low}) must not exceed high ({high})")
+    return max(low, min(value, high))
--- a/tests/test_mathutil.py
+++ b/tests/test_mathutil.py
@@ -1,2 +1,24 @@
 """Tests for mathutil."""
+
+import pytest
+
+from src.mathutil import clamp
+
+
+@pytest.mark.parametrize(
+    ("value", "low", "high", "expected"),
+    [
+        (5, 0, 10, 5),
+        (-1, 0, 10, 0),
+        (11, 0, 10, 10),
+        (0, 0, 10, 0),
+        (10, 0, 10, 10),
+        (3, 3, 3, 3),
+    ],
+)
+def test_clamp_returns_value_within_range(value, low, high, expected):
+    assert clamp(value, low, high) == expected
+
+
+def test_clamp_rejects_inverted_range():
+    with pytest.raises(ValueError, match="must not exceed"):
+        clamp(1, 5, 0)
```
