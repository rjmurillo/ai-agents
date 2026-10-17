# adr-review catch rate

Model: claude-sonnet-5. Trials per cell: 1. Entries: 20.

## Arm: unassisted

| Role | Mentioned | Flagged | Blocked | Errors |
|---|---|---|---|---|
| architect | 7/20 (35%, CI 18% to 57%) | 1/20 (5%, CI 1% to 24%) | 0/20 (0%, CI 0% to 16%) | 0 |
| critic | 8/20 (40%, CI 22% to 61%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| independent-thinker | 6/20 (30%, CI 15% to 52%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| security | 9/20 (45%, CI 26% to 66%) | 2/20 (10%, CI 3% to 30%) | 0/20 (0%, CI 0% to 16%) | 0 |
| analyst | 6/20 (30%, CI 15% to 52%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| high-level-advisor | 4/20 (20%, CI 8% to 42%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| any role | 16/20 (80%, CI 58% to 92%) | 2/20 (10%, CI 3% to 30%) | 0/20 (0%, CI 0% to 16%) | |

## Arm: assisted

| Role | Mentioned | Flagged | Blocked | Errors |
|---|---|---|---|---|
| architect | 4/5 (80%, CI 38% to 96%) | 1/5 (20%, CI 4% to 62%) | 1/5 (20%, CI 4% to 62%) | 0 |
| critic | 3/5 (60%, CI 23% to 88%) | 0/5 (0%, CI 0% to 43%) | 0/5 (0%, CI 0% to 43%) | 0 |
| independent-thinker | 4/5 (80%, CI 38% to 96%) | 0/5 (0%, CI 0% to 43%) | 0/5 (0%, CI 0% to 43%) | 0 |
| security | 3/5 (60%, CI 23% to 88%) | 1/5 (20%, CI 4% to 62%) | 0/5 (0%, CI 0% to 43%) | 0 |
| analyst | 3/5 (60%, CI 23% to 88%) | 0/5 (0%, CI 0% to 43%) | 0/5 (0%, CI 0% to 43%) | 0 |
| high-level-advisor | 4/5 (80%, CI 38% to 96%) | 0/5 (0%, CI 0% to 43%) | 0/5 (0%, CI 0% to 43%) | 0 |
| any role | 5/5 (100%, CI 57% to 100%) | 2/5 (40%, CI 12% to 77%) | 1/5 (20%, CI 4% to 62%) | |

## Arm: control

| Role | Mentioned | Flagged | Blocked | Errors |
|---|---|---|---|---|
| architect | 4/20 (20%, CI 8% to 42%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| critic | 7/20 (35%, CI 18% to 57%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| independent-thinker | 6/20 (30%, CI 15% to 52%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| security | 8/20 (40%, CI 22% to 61%) | 3/20 (15%, CI 5% to 36%) | 0/20 (0%, CI 0% to 16%) | 0 |
| analyst | 6/20 (30%, CI 15% to 52%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) | 0 |
| high-level-advisor | 6/20 (30%, CI 15% to 52%) | 1/20 (5%, CI 1% to 24%) | 1/20 (5%, CI 1% to 24%) | 0 |
| any role | 16/20 (80%, CI 58% to 92%) | 4/20 (20%, CI 8% to 42%) | 1/20 (5%, CI 1% to 24%) | |
