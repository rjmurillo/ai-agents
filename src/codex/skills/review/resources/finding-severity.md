# Finding severity in the rendered review (issue #7351)

Each finding keeps the severity its axis recorded. The axis verdict is a separate result: it comes from the highest finding (`critical` gives `CRITICAL_FAIL`, `high` gives `WARN`), and a label never flows back the other way. A `WARN` axis holding one `high` and one `low` finding renders IMPORTANT and SUGGESTION. A `CRITICAL_FAIL` axis holding one `critical` and one `low` renders CRITICAL and SUGGESTION.

## Mapping

Match the finding's own value case-insensitively.

| Finding value | Severity |
|---|---|
| `critical`, `blocking` | CRITICAL |
| `high`, `non-blocking` | IMPORTANT |
| `medium`, `low`, `polish` | SUGGESTION |
| absent or any other value | UNSPECIFIED |

Axes record `critical|high|medium|low`. The `qa` table also uses `BLOCKING`. Step 4c records a disposition (`blocking`, `non-blocking`, `polish`) and no severity, so its dispositions map as shown.

## Rules

- Print the axis's own value after the label, as `IMPORTANT (high)`, so `medium` and `low` stay distinguishable inside SUGGESTION.
- A finding with no value, or a value outside the table, is UNSPECIFIED. Print the raw value when there is one. Never take the severity from the axis verdict or from a sibling finding.
- A label never claims more than its value can do to the axis verdict. Only `critical` and `high` move it, so `medium` is a SUGGESTION.
- The label is display only. It never feeds `merge_verdicts`, never changes step 6 or step 7, and never touches the blocking-security, `UNKNOWN`, flagged-note, or round-cap rules.
- An axis can hold findings of any label under any verdict. A `CRITICAL_FAIL` axis may list no `critical` finding (a failure trigger, a Stage-1 short-circuit), and a `WARN` axis may list no `high` one (summary context, the 4a downgrade). Report both as recorded.
- Local axes report counts or a gate, not per-finding values. Their findings are UNSPECIFIED.
- Adding, removing, or reordering findings changes no other finding's label.
