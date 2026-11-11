# Code-review catch rate

Model `claude-sonnet-5` via `claude-cli`, run 2026-11-10, 32 entries x 1 trial(s). Calls: 32. Output tokens: 583677. Cost: subscription CLI, no metered spend; dollars not reported.

| Measure | Result (95 percent Wilson interval) |
|---|---|
| Caught in top 5 (same file and class) | 3/32 (9%, CI 3% to 24%) |
| Same file in top 5 (class ignored) | 10/32 (31%, CI 18% to 49%) |

Reviews with no findings: 16. Errored calls (not counted in n): 0.

| Defect class | Caught |
|---|---|
| concurrency | 0/2 (0%, CI 0% to 66%) |
| config-wiring | 0/1 (0%, CI 0% to 79%) |
| edge-case | 2/8 (25%, CI 7% to 59%) |
| error-handling | 0/4 (0%, CI 0% to 49%) |
| logic-error | 1/9 (11%, CI 2% to 44%) |
| resource-handling | 0/1 (0%, CI 0% to 79%) |
| security | 0/2 (0%, CI 0% to 66%) |
| test-defect | 0/5 (0%, CI 0% to 43%) |

| Entry | Class | Caught | Near miss | No findings |
|---|---|---|---|---|
| CR01 | logic-error | 0/1 | 1 | 0 |
| CR02 | error-handling | 0/1 | 0 | 0 |
| CR03 | edge-case | 0/1 | 0 | 1 |
| CR04 | edge-case | 0/1 | 1 | 0 |
| CR05 | resource-handling | 0/1 | 0 | 1 |
| CR06 | edge-case | 0/1 | 0 | 1 |
| CR07 | logic-error | 0/1 | 0 | 0 |
| CR08 | logic-error | 1/1 | 0 | 0 |
| CR09 | test-defect | 0/1 | 1 | 0 |
| CR10 | logic-error | 0/1 | 1 | 0 |
| CR11 | error-handling | 0/1 | 0 | 1 |
| CR12 | error-handling | 0/1 | 1 | 0 |
| CR13 | error-handling | 0/1 | 1 | 0 |
| CR14 | edge-case | 1/1 | 0 | 0 |
| CR15 | logic-error | 0/1 | 0 | 1 |
| CR16 | test-defect | 0/1 | 0 | 0 |
| CR17 | logic-error | 0/1 | 0 | 1 |
| CR18 | security | 0/1 | 0 | 1 |
| CR19 | edge-case | 0/1 | 0 | 1 |
| CR20 | test-defect | 0/1 | 0 | 0 |
| CR21 | edge-case | 0/1 | 0 | 1 |
| CR22 | edge-case | 1/1 | 0 | 0 |
| CR23 | logic-error | 0/1 | 0 | 1 |
| CR24 | test-defect | 0/1 | 0 | 1 |
| CR25 | security | 0/1 | 1 | 0 |
| CR26 | logic-error | 0/1 | 0 | 1 |
| CR27 | concurrency | 0/1 | 0 | 1 |
| CR28 | logic-error | 0/1 | 0 | 1 |
| CR29 | edge-case | 0/1 | 0 | 0 |
| CR30 | test-defect | 0/1 | 0 | 1 |
| CR31 | config-wiring | 0/1 | 0 | 0 |
| CR32 | concurrency | 0/1 | 0 | 1 |
