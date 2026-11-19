# Protected slow-section convention

SkillOpt protects longitudinal guidance from step-level churn by fencing it
in a marker-delimited block. `skillopt.py apply` refuses any edit that would
change content inside the fence. This is the text-space version of slow
weights: fast step edits cannot overwrite hard-won rules.

## The markers

```text
<!-- SLOW_UPDATE_START -->
Durable guidance the optimizer must not touch on a normal step.
<!-- SLOW_UPDATE_END -->
```

- Each marker sits on its own line. Leading and trailing whitespace is
  allowed, so a marker can sit at any indent. Nothing else may share the line.
- A document may hold several fenced sections.
- A `START` with no matching `END`, an `END` with no `START`, or a nested
  `START` is a malformed fence. `apply` exits 2 rather than guessing.

## What `apply` blocks

For any line inside a fence, markers included:

- `replace` is rejected because it would rewrite a protected rule.
- `delete` is rejected because it would drop a protected rule.
- `insert_after` on the `START` marker or on a line inside the fence is
  rejected because the new text would land inside the block.

## What stays allowed

- `append` always lands at the end of the document, outside any fence.
- `insert_after` anchored on the `END` marker lands just after the block.
- Any edit to lines outside every fence.

## When to edit the slow section

Only at epoch boundaries, deliberately, by hand, through the owner's normal
review. Promote a rule into the fence after it has survived many steps. Treat
the edit like changing a pinned project rule: rare, reviewed, never automatic.
