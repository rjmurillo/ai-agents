# Check ADR Constraints Before Implementation

## Rule
Before choosing an implementation language or approach, check relevant ADRs. Especially ADR-042 (Python-first for new scripts).

## Why
PR #1589 session 1 produced a bash `exit_code_handler.sh` that violated ADR-042. The entire implementation was discarded in session 2 and rewritten in Python. One wasted session.

## How
Before writing new scripts, check:
- ADR-042: Python for new scripts (not bash, not PowerShell)
- ADR-035: Exit code standardization (0=success, 1=logic, 2=config, 3=external, 4=auth)
- ADR-006: No logic in YAML