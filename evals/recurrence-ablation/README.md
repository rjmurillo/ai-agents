# Recurring-defect clause ablation (issue #5410)

This run tests whether the recurring-defect bullet in `code-quality.md` changes behavior.

Corpus: `tests/evals/structural-recurrence-ablation-fixtures.json`, two arms, run on 2026-11-06.

Harness: Claude Code 2.1.319, isolated profile, no `--real-home`. Model and grader: `claude-sonnet-5-5`, grader provider `claude-cli`.

## Result

| Arm | Runs | Wrote a test | Semantic pass |
|---|---|---|---|
| With rule | 5 | 5 | 5 |
| No rule | 5 | 0 | 0 |

Fisher's exact test, two-sided: p = 0.008. One later run of the final corpus agreed: the rule arm passed and the no-rule arm failed.

The first five runs also carried a `tests/test_dates.py` path assertion. It failed in both arms, because the agent picked other names such as `test_trailing_z.py`. The corpus no longer pins a test path, so the table counts the semantic verdict and the `Write` tool events.

## Why the earlier control could not separate

`recurring-defect-ablated-no-rule` runs the `implementer` agent, whose prompt asks for tests. Its prompt also stated the test convention. Both arms wrote tests with or without the rule. This pair uses `neutral-editor`, drops the convention from the prompt, and installs `voice.md` in both arms.

## Limits

- This is one task, one model, and one harness. It does not show the clause helps on other tasks.
- The Copilot harness did not run.
- With the rule, the agent also rewrote `feeds.py` and `ingest.py` in all five runs. The request named only `dates.py:31`. The clause says to stay inside the correctness blast radius, and the rubric does not fail this edit.

## Other repaired fixtures

Three fixtures gained `voice.md`, and the skip-tests regex now accepts "added none". Three isolated runs each, 2026-11-06, under the two-of-three bar from ADR-057:

| Fixture | Pass | Two of three |
|---|---|---|
| `explicit-skip-tests-override-is-followed-once` | 3 of 3 | pass |
| `first-occurrence-targeted-fix-only` | 1 of 3 | fail |
| `explicit-skip-tests-override-edit-variant` | 1 of 3 | fail |

`first-occurrence-targeted-fix-only` failed when the reply ended with a handoff to `qa`. The implementer agent required that line in every reply. It now applies only to delegated tasks. Three later isolated runs passed 3 of 3.

`explicit-skip-tests-override-edit-variant` still passes 1 of 3 after that change. The replies say tests were skipped but do not state the lost coverage. One reply also omitted the `dates.py:31` line reference. This is a behavior miss, so the rubric stays as written.

The Copilot harness could not run. Copilot CLI 1.0.105 removed `--no-remote`, which the runner passes, so each launch exits with an error.
