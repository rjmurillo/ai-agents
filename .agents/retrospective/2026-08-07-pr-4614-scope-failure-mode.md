# Retrospective: PR #4614 Silent Scope Gate Pass on Git Failure

## Context

PR #4614 (fix/scope-merge-check) establishes fail-closed behavior for unknown scope.
A review thread identified that two helper functions (`get_head_files_against_ref`,
`get_index_files_against_ref`) returned `[]` on git failure instead of raising
`ScopeDetectionError`, allowing a git failure during an in-progress merge to silently
pass the scope gate with 0 files.

## Learning

Subprocess helpers that return default values on failure create silent-pass antipatterns.
When a caller needs to distinguish "empty result" from "could not compute result,"
the helper must raise rather than return a sentinel.

## Action Taken

Both functions now raise `ScopeDetectionError` with stderr context. Tests updated
from asserting `== []` to `pytest.raises(ScopeDetectionError)`. 57/57 tests pass.
