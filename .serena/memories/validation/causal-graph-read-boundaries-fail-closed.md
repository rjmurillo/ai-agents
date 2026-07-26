# Causal graph reads must fail closed

## Rule

Read the causal graph directly. Treat only `FileNotFoundError` as absence. Any other `OSError` means existing state could not be read, so mutation must stop.

## Hook boundary

Snapshot with `Path.read_bytes()` before mutation. `FileNotFoundError` yields no snapshot. Every other `OSError` returns exit code 2 before `_apply_causal_graph_updates` runs.

## Why

`Path.is_file()` can convert permission and other stat failures into `False`, making an unreadable graph look absent. A check-then-read sequence also adds a race.

## Evidence

Issue #3388. Commits 42d52c2bd3 and a148c51c6c. Focused canonical and generated tests cover missing files, unreadable files, and snapshot failure before mutation. Follow-up issue #3389 tracks snapshot restoration failures.