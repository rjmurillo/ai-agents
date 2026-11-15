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

## Local scanner values

The `golden-principles` and `taste-lints` scanners (local axes 3 and 4) print a `severity` on each item of the JSON `violations` array. Their values are `error` and `warning`. Map them by their effect on the axis verdict: `adapt_local_axis_verdict` turns a positive `error_count` into `FAIL`, which `merge_verdicts` turns into `CRITICAL_FAIL`, and it turns a positive `warning_count` with no errors into `WARN`.

| Scanner value | Severity |
|---|---|
| `error` | CRITICAL |
| `warning` | IMPORTANT |

## Doc-accuracy values

`doc-accuracy` (local axis 2) prints a `severity` of `critical`, `high`, `medium`, `low`, or `info` on each finding. The axis is a gate, and the review runs it without `--severity-threshold`, so the default `high` applies. A finding at or above `gate_result.threshold` turns the gate to `FAIL` (exit 10), which `adapt_local_axis_verdict` reports as `FAIL` and `merge_verdicts` turns into `CRITICAL_FAIL`. Label such a finding CRITICAL, so at the default threshold `critical` and `high` render CRITICAL, not the IMPORTANT the table gives `high` on other axes. A finding below the threshold cannot move the verdict, so it follows the table: `medium` and `low` render SUGGESTION. `info` marks a finding outside the diff, which never blocks, and renders UNSPECIFIED.

## Rules

- Print the finding's own value after the label, as `IMPORTANT (high)`, so `medium` and `low` stay distinguishable inside SUGGESTION.
- A finding with no value, or a value outside the table, is UNSPECIFIED. Print the raw value when there is one. Never take the severity from the axis verdict or from a sibling finding.
- A label never claims more than its value can do to the axis verdict. `critical`, `blocking`, scanner `error`, and a `doc-accuracy` finding at or above the gate threshold can fail the axis. `high`, `non-blocking`, and scanner `warning` can make it `WARN`. `medium`, `low`, and `polish` cannot move it, so they are SUGGESTION.
- The label is display only. It never feeds `merge_verdicts`, never changes step 6 or step 7, and never touches the blocking-security, `UNKNOWN`, flagged-note, or round-cap rules.
- An axis can hold findings of any label under any verdict. A `CRITICAL_FAIL` axis may list no `critical` finding (a failure trigger, a Stage-1 short-circuit), and a `WARN` axis may list no `high` one (summary context, the 4a downgrade). Report both as recorded.
- A local axis with a section above takes its labels from that section, which overrides the value table. A local axis with no section above (`code-qualities-assessment`) reports scores and an exit code, not a per-item value, so its findings are UNSPECIFIED.
- Adding, removing, or reordering findings changes no other finding's label.
