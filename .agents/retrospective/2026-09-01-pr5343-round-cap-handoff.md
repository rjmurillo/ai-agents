# Retrospective: pr5343-round-cap-handoff

## Session Info

- **Date**: 2026-09-01
- **Agent**: Claude Code (Claude Sonnet 5)
- **Task Type**: Take over PR #5343 (`claude/fix-4632-build-all-check-fails-open`) after `pr-autofix`'s round-cap breaker tripped (6 rounds recorded, cap 5; 9.3h wall clock, cap 4.0h) and explicitly asked for human/session review.
- **Outcome**: Success

## Phase 0: Data Gathering

The round-cap breaker comment named no specific failure, only that automated
work had stopped. `Run Python Tests` was red on the PR's head commit
(`a8784605e`), and five Copilot review comments had landed against that same
commit within the prior few minutes.

## Phase 1: Insights Generated

### Finding: a production signature change landed without updating its own test's mock

`a8784605e` added a keyword-only `missing_root_ok` parameter to
`_strict_owned_stat` in `build/scripts/build_all.py`, but
`test_run_check_aborts_before_generation_when_owned_file_stat_fails` still
monkeypatched it with a two-positional-argument stub
(`flaky_strict_owned_stat(path: Path)`). The mismatch is a `TypeError` at
call time, not a logic disagreement, so it failed loudly in CI
(`pytest (bulk-nested)`, `Run Python Tests`) rather than passing for the
wrong reason: `FAILED
test_run_check_aborts_before_generation_when_owned_file_stat_fails -
TypeError: ... got an unexpected keyword argument 'missing_root_ok'`.

**Classification**: a contract change (new required keyword argument) was
not mirrored into every caller, including a test's own stand-in for the
changed function. `.claude/rules/testing.md` SHOULD-4 names exactly this
obligation ("grep for tests asserting old contracts... and flip them in the
same diff").

### Finding: two tests mocked above the boundary they meant to prove

Both `test_run_check_aborts_before_generation_when_owned_file_stat_fails`
and its directory-scan sibling replaced `_strict_owned_stat` /
`_strict_owned_children` outright with a stub that raised the *already
wrapped* `SnapshotIncompleteError`, rather than raising a raw `OSError` at
the real I/O boundary (`Path.stat`, `os.scandir`) and letting production
code perform the wrapping. Copilot's review caught this precisely: deleting
the `except OSError` translation in either real function would leave both
tests green, because neither test's code path ever reaches it.

**Cost avoided, not incurred**: this was caught by review before merge, not
after. Rewriting both tests to fail at the true I/O boundary (verified with
a negative control: reverting `_queue_strict_owned_path` to a no-op made
`test_run_check_aborts_before_generation_when_owned_file_stat_fails` fail as
expected) closes the gap `.claude/rules/testing.md` SHOULD-6 describes
("prove the wiring, not only the guard").

## Phase 2: Remediation

1. Rewrote both tests to monkeypatch `Path.stat` and `os.scandir` directly,
   matching the file's existing pattern for `Path.read_bytes`
   (`_fail_read_bytes_for`).
2. Added an `assert metadata is not None` in `_queue_strict_owned_path` to
   resolve a real mypy `union-attr` finding: `_strict_owned_stat` returns
   `os.stat_result | None`, and `missing_root_ok=False` makes `None`
   unreachable but mypy cannot infer that from the signature alone.
3. Corrected `.claude/skills/ai-agents-diagnostics-toolkit/SKILL.md`'s
   exit-code table, which omitted exit 3 entirely and still described
   `build_all.py --check` exit 2 as only config/staleness after an earlier
   commit on this same PR had already split unreadable-owned-file into
   exit 2 and git-state-unreadable into exit 3. Regenerated the Copilot
   mirror.

All 117 tests in `tests/build_scripts/test_build_all.py` pass; `mypy` is
clean on both changed Python files; `scripts/validation/pre_pr.py` reports
`RESULT: All validations passed`.

## Phase 3: Process Observation

This is the second time in one session that a fix landed on this same PR
mid-flight from a different concurrent `pr-autofix` session, without
either session holding a lease at push time. The round-cap breaker is a
useful backstop (it stopped automated work rather than looping past the
cap), but nothing prevented the commit that tripped it from shipping a
real CI regression in the first place. Issue #5447, filed independently
during this same window against a different PR (#5344), proposes exactly
the kind of unpushed/unverified-commit safeguard that would generalize
here; worth linking from a follow-up if #5343's own history is reviewed.
