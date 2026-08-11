# Add the Missing State, Do Not Overload a Sentinel

**Last Updated**: 2026-08-04
**Source**: Four measured instances in one session

## Constraint (HIGH confidence)

This repo ships the same defect repeatedly: a status value carries two meanings,
one of which is "we never found out." The zero, the empty string, or the success
exit code then reads as a measurement, and everything downstream trusts it.

Four instances reached `main`, each in different code, within a single session:

| Site | Overloaded value | What it hid |
|---|---|---|
| `extract_session_episode.py` (#3972) | `tool_calls: 0`, `duration: 0` | The session was never measured, so dashboards averaged real zeros against unknowns |
| `memory-index.md` (#4441) | `(0)` token count | A reader budgeting context reads "empty, skip it" |
| Copilot auth probe (#4504) | boolean pass/fail | "Cannot determine" collapsed into pass, so the gate failed open |
| `memory_index_token_ratchet.py` | exit `0` | Missing `tiktoken` would have made the gate green by checking nothing |

The pattern is always the same shape: a two-valued type is asked to carry three
states. The fix is always the same too, and it is cheap. Add the third state.

## Second measurement

An adversarial review on 2026-08-05 found five more collapsed states in gates
merged during the same campaign:

| Site | Overloaded value | What it hid |
|---|---|---|
| Documentation portability gate (#4628) | deduplicated script list | One baselined invocation also allowed repeated identical invocations |
| CLI E2E gate (#4629) | exit `0` | Neither supported CLI existed, so no E2E test ran |
| CLI E2E gate (#4629) | exit `0` | `SKIP_CLI_E2E=true` bypassed a required gate |
| Subprocess encoding gate (#4630) | empty file list | Git reported zero tracked scripts, so no source was inspected |
| Unreachable-code gate (#4631) | empty file list | Git reported zero Python files, so no source was inspected |

Each reproduced against `origin/main` with an attached worktree. Regression
tests then killed mutations that restored the false-pass branch.

## Rule

When a function reports a measurement, a status, or a verdict, ask whether
"unknown" or "not measured" is reachable. If it is, give it its own value:
`None` rather than `0`, a third enum member rather than a boolean, exit `2`
rather than `0` or `1`.

Two corollaries earned the hard way:

- **A gate that cannot check must not exit zero.** Green-because-unchecked is
  worse than no gate, because it also removes the pressure to add one. Exit
  non-zero and name the missing dependency. When the dependency is locked in
  `pyproject.toml`, its absence is a broken environment, not a routine skip.
- **Say so in the tests.** Name the test for the state, not the value:
  `test_tool_calls_none_for_modern_session`, never `..._zero_...`. A test named
  after the sentinel silently re-encodes the bug when someone fixes it, and
  that is exactly what happened: six tests in a second, independent suite
  asserted the zero contract and turned red on the fix.

## Cost of getting it wrong

None of the four was caught by review. All four were caught by a downstream
consumer behaving oddly, which is the expensive end. The defect is invisible in
a diff because the code looks complete: it returns a value of the right type on
every path.
