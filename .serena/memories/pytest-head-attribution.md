# Pytest HEAD mutation attribution

The root `conftest.py` guard uses two per-test Git signals:

- `GIT_REFLOG_ACTION` is checked only in the project `HEAD` reflog. This catches successful porcelain changes without treating unrelated branch reflogs as proof.
- `GIT_TRACE2_EVENT`, `GIT_TRACE_REFS`, and `GIT_TRACE_SETUP` write to one UUID-named file. Trace2 identifies the process session, setup identifies the effective worktree and Git directory, and ref tracing proves a successful `HEAD` transaction or `create_symref`.

Do not infer causality from command shape for general ref writes. `update-ref --stdin` hides its target, and any unrelated branch write can coincide with an external commit. Exact ref-database transactions are the causal evidence.

Git 2.55 is one narrow exception: `git symbolic-ref` can emit `transaction_prepare` and exit 0 without a ref-transaction finish record. For that command only, parse the documented symbolic-ref argv forms after confirming the Trace2 session succeeded and targeted the project. Ignore read-only calls and writes to refs other than `HEAD`.

Repository scoping must handle the project worktree, explicit `--git-dir`, `GIT_DIR`, and linked worktree `.git` files. Guard-owned Git reads strip every attribution variable so they never contaminate the test trace. Missing or malformed evidence fails closed when HEAD changed.

Git reflog expiry emits one unprefixed continuation line shaped `^ \d+: -?\d+$`. Accept only that known continuation. Keep arbitrary malformed lines fail-closed.

Use one trace file under `tempfile.gettempdir()`, keep its filename Windows-safe, restore prior environment values, and unlink it in `finally`.

Implemented in PR #3125. Contracts live in `tests/test_pytest_head_guard.py`; Windows execution remains protected by `tests/workflows/test_pytest_head_guard_windows.py`.

## Eureka

Command execution is not proof of mutation. Ref-database transactions are. This removes both the unrelated-ref false blame and the `--stdin` false negative with one evidence model.

## Instrumentation trust boundary

Tests are trusted to inherit the guard's Git instrumentation. A subprocess that replaces its environment and strips every guard marker is observationally identical to an external process. Treating every unattributed HEAD move as test-caused would recreate the #3109 false positives, so readable but unattributed moves remain warnings.