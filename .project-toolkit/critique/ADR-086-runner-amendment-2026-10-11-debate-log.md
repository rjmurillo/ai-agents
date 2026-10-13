# ADR Debate Log: ADR-086 lefthook_runner.py Amendment

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final Status**: accepted (ADR-086 stays accepted; text amended)
- **Panel**: reduced, architect and critic. See "Panel basis" below.
- **Issue**: #5989. **Trigger**: PR #5988 set `lefthook.yml` line 4 to
  `lefthook: python3 scripts/validation/lefthook_runner.py`. ADR-086 still named
  `uv run --frozen lefthook` in decision item 5, Implementation Notes, and
  Confirmation.

## Panel basis

AGENTS.md picks the full panel only when the change touches executable
enforcement or a rule other gates read. This edit touches neither.
`lefthook_runner.py`, its tests, and `lefthook.yml` already landed in PR #5988.
This change makes prose match them. No script, validator, or gate reads the
edited ADR text (searched `scripts/`, `tests/`, `build/` for `ADR-086`; every
hit is a citation in a comment or message, none parses the ADR body).
The reduced panel of architect and critic applies.

Independence limit: the architect and critic passes below were run by the
authoring agent in separate steps. They are not independent reviewers. The
repository owner decides the item 5 design choice when reviewing the PR for
issue #5989. The checks that do not depend on the author are the 19 passing tests in
`tests/test_lefthook_runner.py` and the runner behavior read from
`scripts/validation/lefthook_runner.py`.

## Round 1 Summary

### Evidence verified

- `lefthook.yml:4` sets `lefthook: python3 scripts/validation/lefthook_runner.py`.
- `lefthook_runner.py` resolution order: `uv run --frozen lefthook` when the
  `version` probe exits 0, then `lefthook` on `PATH`, then
  `node_modules/.bin/lefthook`, else a diagnosis and exit 3.
- `tests/test_lefthook_integration.py` asserts on every platform, Windows
  included, that the shim contains
  `python3 scripts/validation/lefthook_runner.py "$@"` after the
  `LEFTHOOK_BIN` guard and before the `PATH` fallback (issue #5491, PR #6428).
  The earlier Windows carve-out citing issue #3289 misread a truncated
  assertion, so the amendment carries no platform scoping.
- Item 6 (`uv run --frozen lefthook install --reset-hooks-path`) is run by a
  developer or setup script, never through a generated shim. The runner does not
  change it. README.md, CONTRIBUTING.md, and the integration tests all use the
  direct command.
- Confirmation commands that call `uv run --frozen lefthook` directly stay valid
  because they test the pinned runtime, not the shim.

### Key Issues Addressed

- Architect: item 5 named a command the config no longer sets. The amendment
  names the runner and records the fallback order, so the ADR matches the code.
- Architect: item 5's guarantee, that a `PATH` binary cannot silently replace the
  configured runtime, still holds. The frozen uv runtime wins whenever its probe
  passes. A `PATH` binary runs only when uv cannot resolve Lefthook.
- Critic: the new fallback widens what item 5 allowed. Resolved by stating the
  fallback and its precedence in the Decision, not only in Implementation Notes.
- Critic: the Review Triggers bullet "Hook execution stops using the frozen uv
  environment" no longer describes the runner. Reworded to cover a change in
  preference or fallback order.
- Critic: the shim claim was first scoped to POSIX. The review found the
  integration test checks the shim order on Windows too, so the scoping was
  removed and the text cites issue #5491 and PR #6428.
- Critic: Confirmation never exercised the runner. Added the runner `version`
  command and `tests/test_lefthook_runner.py`.

### Major Changes Made

- Decision item 5 rewritten for the runner and its fallback chain.
- Installation and Version Ownership paragraph rewritten; states item 6 is
  unchanged.
- Confirmation block adds `python3 scripts/validation/lefthook_runner.py version`
  and `tests/test_lefthook_runner.py`.
- Review Triggers bullet reworded.
- Update History row added.

### Noticed, outside this amendment

- ADR-086 still says the Lefthook pin is 2.1.10 in several places;
  `pyproject.toml` now pins `lefthook==2.1.17`.
- The 2026-08-31 debate log lists an open item: the acceptance procedure's
  linked-worktree leniency text and its wrong issue #2374 citation.
- Confirmation still lists `lefthook check-install`, which the 2026-08-31 debate
  removed from the gate.

None of these is part of issue #5989. They are recorded for the owner.

### Agent Positions

| Agent | Position |
| --- | --- |
| architect | Accept. The text now matches `lefthook.yml` and the runner, and item 5's no-silent-replacement guarantee is preserved. |
| critic | Accept after changes. Review Triggers wording, and runner confirmation were added. No open P0 or P1. |

### Next Steps

Owner review of the PR. No further rounds.
