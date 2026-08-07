# Retrospective: PR #4609 Review Thread Resolution

## Session Context
- **PR**: #4609 (fix(validation): isolate portability git and restore mutants)
- **Session**: 10004
- **Date**: 2026-08-07

## Learnings Captured

### Docstring-Contract Drift in Mutation Harnesses
When adding `expected_outcome` to a mutation dataclass, the module docstring
must be updated to reflect the new exit-code semantics. The old contract
("exit 0 = every mutant DEAD") became misleading once cosmetic controls
legitimately expect SURVIVED while still exiting 0.

### Synthetic CompletedProcess Objects Need Caller Awareness
`_purge_pycache()` returns a synthetic `CompletedProcess` with `args=["purge", ...]`
and rc=4. Downstream classifiers that assume every `CompletedProcess` came from
pytest will misattribute the error. Guard classifiers against non-pytest processes
by checking `proc.args` before interpreting return codes as pytest exit codes.
