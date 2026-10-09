# ADR Debate Log: ADR-101 and ADR-090 stale-fact corrections after the test selector retirement

Panel: reduced (architect and critic). The edits correct facts and label history. They change no requirement, so the AGENTS.md trigger for the full panel does not apply.

## Summary

- **Rounds**: 1, plus fixes verified against the branch head
- **Outcome**: Consensus (architect Block resolved by the fixes below; critic Disagree-and-Commit)
- **Final Status**: ADR-101 stays accepted. ADR-090 status unchanged.

## Scope

PR #6241 (closing issue #6239) retired the import-graph test selector. That left stale facts:

- ADR-101 said `.github/CODEOWNERS` had "five globs". It has 50 rules today, all `@rjmurillo`.
- ADR-101 cited `pytest.yml` line numbers that moved, and described `skip-tests` as live. That job is gone.
- ADR-101 credited the retirement to "PR #6239". That is the issue; the pull request was #6241.
- ADR-090 told readers to use the pre-push pytest selector, which no longer exists.

## Round 1 Summary

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Block | Cites matched `origin/main` but this branch adds 2 lines to `pytest.yml`, so cites after line 108 were off by 2 |
| critic | Disagree-and-Commit | `pytest.yml:663` named a comment line; the `if:` is at 665 |

### Key Issues Addressed

- P1: `test-result` `!cancelled()` cite pointed at a comment line.
- P1: three `pytest.yml` cites were off by 2 on the branch head.
- P2: the `pytest.yml:260-263` range missed the comment that states requirement 1.
- P2: "PR #6241 (issue #6239)" nested parentheses.
- P2: one historical sentence mixed past and present tense.

### Major Changes Made

- `pytest.yml:663` became `:665`, and `650-663` became `652-665`.
- The `setup-code-env` list became `130,170,237,322,496,588,730`.
- `pytest.yml:260-263` became `262-266`.
- The amendment heading now reads "PR #6241, which closed issue #6239"; other mentions say "PR #6241".
- The round-9 sentence now uses past tense.

Each new line number was read from `.github/workflows/pytest.yml` on the branch head before commit.

## Verified facts

- `.github/CODEOWNERS` has 50 rules; `/scripts/ci/` is line 61 and `/tests/.test_durations` is line 63.
- `pytest.yml:67` and `:83-91` match the `check-paths` output and the `determine` step.
- `scripts/ci/ruleset_required_contexts.py:16` holds "Run Python Tests".
- Requirement 1 keeps its meaning: the `test` job has no job-level `if:` or `needs:`.
