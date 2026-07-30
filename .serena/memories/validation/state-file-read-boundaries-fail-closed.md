# State-file reads must fail closed before mutation

## Rule

Read the state file directly. Treat only `FileNotFoundError` as absence. Any
other `OSError` means existing state could not be read, so mutation must stop.

## Hook boundary

Snapshot with `Path.read_bytes()` before mutation. `FileNotFoundError` yields no
snapshot. Every other `OSError` returns exit code 2 before the mutation runs.

## Why

`Path.is_file()` can convert permission and other stat failures into `False`,
making an unreadable file look absent. A check-then-read sequence also adds a
race.

## Evidence

Issue #3388. Commits 42d52c2bd3 and a148c51c6c. The original subject was
`scripts/validation/merge_causal_graph.py` and its `_apply_causal_graph_updates`
mutation. That file was deleted by ADR-089 (the causal graph had no reader), so
the code is reachable only in git history. Focused canonical and generated tests
covered missing files, unreadable files, and snapshot failure before mutation.
Follow-up issue #3389 tracks snapshot restoration failures.

The rule generalizes to any JSON or text state file a hook mutates in place; it
was never specific to the graph.
