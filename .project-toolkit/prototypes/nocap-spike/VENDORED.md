# Vendored code provenance (SPIKE ONLY)

This directory is a spike. It lives under `.project-toolkit/prototypes/` because the repo root allows no new top-level entries. Nothing here ships, and nothing here is wired to a hook.
The vendored name and marks belong to their author. This spike does not use them for anything shipped.

## Source

- Upstream: `https://github.com/jedbrnth-eng/no-cap`
- Commit: `a683c857d0aa547cdc9baace6082a24b4016d0b8` (committed 2026-11-21, release 0.3.1)
- License at that commit: Apache-2.0. `vendor/LICENSE` and `vendor/NOTICE` are copied unchanged.
- Files taken from `nocap/`: `__init__.py`, `claims.py`, `evidence.py`, `verdict.py`, `tamper.py`, `lang.py`.
- `lang.py` is included because `claims.py` imports it.

## Changes from upstream

Apache-2.0 section 4(b) asks that modified files say so. Each change is listed here.

1. `claims.py` lines 69 and 375 (68 and 374 upstream): four literal dash characters (code points U+2014 and U+2013) became
   Python Unicode escape sequences. The repo bans those bytes in `.py` files. The compiled regex and token
   set are unchanged. Line 1 of `claims.py` now carries a one-line modification notice.
2. No vendored `.py` file carries a lint suppression comment. Instead `pyproject.toml` sets
   `per-file-ignores = ["ALL"]` and a `ruff format` exclude for `vendor/**`. The pre-commit hook runs
   `ruff check --fix`, which would otherwise rewrite upstream code.

## Check that the changes are behavior-neutral

Upstream's own tests ran against the modified files in a scratch copy of the upstream checkout.
Result on 2026-11-23, rerun on the committed files after the notice line was added: `156 passed` for `test_claims.py`, `test_evidence.py`, `test_claim_regressions.py`,
`test_cross_turn.py`, `test_verdict.py`, and `test_suite_tamper.py`.
