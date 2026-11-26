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

1. `claims.py` lines 71 and 377 (68 and 374 upstream): four literal dash characters (code points U+2014 and U+2013) became
   Python Unicode escape sequences. The repo bans those bytes in `.py` files. The compiled regex and token
   set are unchanged. Line 1 of `claims.py` now carries a one-line modification notice.
2. No vendored `.py` file carries a ruff suppression comment. Instead `pyproject.toml` sets
   `per-file-ignores = ["ALL"]` and a `ruff format` exclude for `vendor/**`. The pre-commit hook runs
   `ruff check --fix`, which would otherwise rewrite upstream code.
   Upstream is untyped. The last line of `claims.py`, `evidence.py`, `lang.py`, `tamper.py`, and `verdict.py`
   is `# mypy: ignore-errors`. It sits last so no cited line number moves.
   A `pyproject.toml` mypy override did this before. The strict-baseline test rejects that override shape.
   The taste-lint ratchet has no path exclude, so it needs comments in the files themselves.
   `claims.py`, `evidence.py`, and `verdict.py` gained two `# taste-lint: ignore` lines after line 1, and `lang.py` gained one at line 1.
   These are comments only.

3. `evidence.py`, spike round 2. These change behavior on purpose. Line 1 carries a modification notice.
   - `parse_git`: the `git merge` pattern ends in `merge(?![\w-])`, so `git merge-tree` and `git merge-base`
     no longer count as a merge.
   - `extract`: `ev["shas"]` reads SHAs from the tool output only. Upstream also read the command text.
4. Spike round 3, in `evidence.py`, `verdict.py`, and `claims.py`. These change behavior on purpose.
   Line 1 of each file carries a modification notice.
   - `evidence.py`: `sha_refs` keeps SHAs the output places as a commit, HEAD, or ref.
     `_repo_pr_scripts`, `_pr_checks_script`, and `_pr_states` read this repo's `merge_pr.py`,
     `get_pr_checks.py`, and PR-create output, plus PR states in `gh` JSON and `gh pr list` rows.
     `parse_git` records the ref a `git merge` names. `_ci_status` keeps its counts.
   - `evidence.py` freshness: `->` and `=>` are not redirects. `$VAR` targets are not code.
     Heredocs written to temp or doc files are skipped. Relative writes after `cd` into a `mktemp`
     directory are skipped. `git merge-tree` is not a merge. `scratch*/` paths are temp.
     Python string targets need an extension that starts with a letter.
   - `verdict.py`: `_sha` needs a placed SHA and never credits a sentence about what a commit did.
     `_merged` drops a local `git merge` for a PR merge claim, and accepts `pr_states`.
     `_pr_opened` accepts an OPEN state for "PR #N is open". `_ci` compares stated check counts.
     The new parsers never yield CAP.
   - `claims.py`: a sentence with check counts and no test words becomes a `ci` claim.
   - Upstream's `tests/test_redos.py` caught two quadratic SHA regexes in the first round 3 draft. The field
     pattern is anchored to a word start with bounded runs, and the row pattern no longer spans lines.

## Check that the changes are behavior-neutral

Changes 1 and 2 are behavior-neutral. Changes 3 and 4 are not. Upstream's tests still pass with them:
`156 passed` on 2026-11-25.

Upstream's own tests ran against the modified files in a scratch copy of the upstream checkout.
Result on 2026-11-23, rerun on the committed files after the notice line was added: `156 passed` for `test_claims.py`, `test_evidence.py`, `test_claim_regressions.py`,
`test_cross_turn.py`, `test_verdict.py`, and `test_suite_tamper.py`.
