# Closure scan caches key on the path as given

PR #6878 (merge 68cf87ef34, 2026-10-23) memoized the dynamic-load scan in closure and dispatch code.

## Where the behavior lives

- The docstring of `_memoized_dynamic_loads` in `run_completion_gate.py` owns the cache-key contract.
- It keys on `(script, source)` and does not resolve `script`.
- This memory keeps the evidence for that choice.

## Evidence

- Under ADR-119, `.claude/skills/<name>` is a symlink into `src/claude/skills/<name>`.
- A dynamic load built from `__file__` resolves differently by spelling.
- Only the symlinked spelling is reported as unresolvable.
- A resolved-path key merged the two spellings and changed the verdict.
- A mutation run with the resolved key failed 2 tests.

## Callers

- `_dynamic_loads` in `run_completion_gate.py` is the scan being cached.
- `closure_manifest.py` shares one `load_cache` between the closure pass and the site pass.
- `scripts/ci/verify_dispatch_closure.py:322,325` repeats the same two scans.
- That caller could share the cache the same way. This is noted, not done.
- Issue #6734 closed on 2026-10-24 without this change.
