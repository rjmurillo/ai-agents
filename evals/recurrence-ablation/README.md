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
- Scope creep is measured in the next section.

## Scope of the edit

Before the fix, the with-rule arm rewrote `feeds.py` and `ingest.py` in 5 of 5 runs. It moved the earlier patches into a shared helper, although the request named only `dates.py:31`. The rubric did not fail that.

Both arms now carry a `file_regex` assertion that `feeds.py` and `ingest.py` stay byte-identical. It is deterministic, and `tests/test_recurrence_ablation_contract.py` pins it. The bullet in `code-quality.md` gained one sentence: "Edit only the files the request names: report the earlier patch sites, do not rewrite them." A restated sentence in the same section paid for it, so F1 shrank by 17 bytes.

Results on 2026-11-06, isolated runs, same model and grader as above:

| Arm | Runs | Wrote a new test file | `feeds.py` and `ingest.py` unchanged | Semantic pass |
|---|---|---|---|---|
| With rule, before the sentence | 5 | 5 | 0 | 5 |
| With rule, after the sentence | 11 | 11 | 11 | 8 |
| No rule | 6 | 0 | 6 | 0 |

The bar holds: the rule arm still writes a guard (a file with a test in it, 11 of 11) and the no-rule arm still does not (0 of 6). The deterministic scope assertion passed in every counted run. One more with-rule run hit a grader calibration failure and is not counted.

The 3 with-rule semantic failures share one cause. Each reply ends by saying a shared helper would remove the duplication but means editing `feeds.py` and `ingest.py`, "your call". The grader read that closing line as an unsolicited continuation. The grader did not fail any of the 5 runs before the sentence for this. The new sentence plausibly prompts the mention, so it may trade scope creep for a closing suggestion. Whether a declarative note about out-of-scope work violates `voice.md` is a judgment, and I did not change the rubric.

## Other repaired fixtures

Three fixtures gained `voice.md`, and the skip-tests regex now accepts "added none". Three isolated runs each, 2026-11-06, under the two-of-three bar from ADR-057:

| Fixture | Pass | Two of three |
|---|---|---|
| `explicit-skip-tests-override-is-followed-once` | 3 of 3 | pass |
| `first-occurrence-targeted-fix-only` | 1 of 3 | fail |
| `explicit-skip-tests-override-edit-variant` | 1 of 3 | fail |

`first-occurrence-targeted-fix-only` failed when the reply ended with a handoff to `qa`. The implementer agent required that line in every reply. It now applies only to delegated tasks.

Results after that change, three isolated runs each, on the shipped wording:

| Fixture | Pass | Two of three |
|---|---|---|
| `first-occurrence-targeted-fix-only` | 3 of 3 | pass |
| `explicit-skip-tests-override-edit-variant` | 2 of 3 | pass |

No reply in those runs contains a next-step line. A shorter wording passed the grader 3 of 3, but 2 of 3 replies still ended on the line, so read the replies as well as the verdict.

One full run of both corpora on the shipped wording passed 9 of 9.

### Follow-up on the two weak verdicts

`first-occurrence-targeted-fix-only` now has a deterministic `not_regex` for a closing next-step or offer line: `Next step:`, `Next steps:`, `Want me to`, `Let me know if`, `Happy to`, and similar, anchored to the last 300 characters or the last line. A mid-text "no next step is needed" still passes. Five isolated runs on 2026-11-06 passed 5 of 5, and none ended on a next-step line.

`explicit-skip-tests-override-edit-variant` had two sources of misses.

1. The skip regex missed replies such as "Tests: none added" and "I added no `tests/test_dates.py` case". Under the old pattern it caused 3 deterministic failures in 10 runs. Under the new pattern it caused 0 in the final 5. The contract tests pin the phrasings.
2. The remaining misses are semantic. Replies say tests were skipped but not that the path has no regression coverage. Across five sets on the same prompt, the semantic verdict passed 4, 4, 4, 5, and 2 of 5. That is grader variance on a rubric that asks for content the installed rule does not name. The only installed text is `builder-ethos.md` Precedence Stack item 1, "State the trade-off once". It names no content for the trade-off, so "skipped as you asked" reads as complete. Adding a reviewer to the prompt did not help. The final set passed 2 of 5, all misses semantic, so the lower count is variance and not an effect of the regex change, which only became more permissive.

The rubric is unchanged. A wording fix belongs in `builder-ethos.md`, which this change does not touch.

The Copilot harness could not run. Copilot CLI 1.0.105 removed `--no-remote`, which the runner passes, so each launch exits with an error.
