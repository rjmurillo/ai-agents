# Implementer prompts must forbid ending a turn at interim status

## What happened

In the 2026-09-29 P1 sweep, implementer prompts said "drive to merge; do not end at interim status". Early prompts lacked a line that says "do not end your turn at an interim status". Agents on #5485 and #5477 ended turns at interim CI status several times and needed resume messages.

The record does not show whether later prompts that included the line stopped the behavior. Treat the fix as a hypothesis until a run with and without the line is compared.

## Practice

Put "do not end your turn at an interim status; wait for CI and continue to merge or a named blocker" in every implementer prompt that says drive to merge. Count resume messages per PR in the next sweep to test it.

## Source

P1 sweep 2026-09-29, issues #5485 and #5477 (closed by #5992 and #5994).
