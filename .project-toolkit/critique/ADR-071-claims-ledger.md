# ADR-071 claims ledger

Verified 2026-11-22 for issue #7493.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| The reserved recall group reports failure and exits zero. | Behavior | Run the copied plugin's registered command with its recall shim moved aside. | Exit zero, empty stdout, and two stderr lines. |
| The dispatcher suppresses a blocking decision from the recall shim. | Behavior | Run `tests/hooks/test_dispatch_prompt_preserving.py`. | The reserved group suppresses the decision. The control retains the other group's blocking behavior. |
