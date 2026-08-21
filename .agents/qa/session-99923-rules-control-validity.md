---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99923-2dd747176-rules-control-validity.json
qaCommit: cbb105059da3bea423c5d17dbcc217b0b59c6712
---

# QA Report: testing.md control-validity rule (issue #5187)

- Issue: #5187
- Branch: `claude/issue-5187-control-validity`
- Session log: `.agents/sessions/2026-08-21-session-99923-2dd747176-rules-control-validity.json`
- QA commit: `cbb105059da3bea423c5d17dbcc217b0b59c6712`

## Verdict

PASS.

## Scope under test

One item added to `.claude/rules/testing.md` (SHOULD 17) and the two
instruction mirrors regenerated from it. No code, no test, no workflow.

## What "tested" means for a rule change

There is no runtime behavior here, so the checkable properties are the ones the
repository already gates. Each was run rather than assumed:

| Property | Command | Result |
|---|---|---|
| Mirrors match the rule, so no tree is stale | `build/scripts/build_all.py --check` | no staleness after commit |
| Always-on instruction budget is untouched | `scripts/validation/instruction_budget.py` | PASS, all four language rows |
| Repository-wide validation | `scripts/validation/pre_pr.py` | all validations passed |
| Session log is well formed and its SHA reachable | `scripts/validate_session_json.py` | PASS |

The budget check is the one that could have failed. The `.py` always-on row had
764 bytes of headroom, so adding this item to an always-on rule such as
`code-quality.md` would have broken every contributor's push. `testing.md` is
path-scoped to test trees, so its bytes never enter that budget. Verified by
reading the generated frontmatter rather than assuming the scope survived
generation: both mirrors carry the test-tree `applyTo`, not `**`.

## What is deliberately not claimed

The rule is guidance for authors. Nothing enforces it, and this report does not
claim otherwise. `.claude/rules/` is the binding surface across Claude, Codex,
and Copilot per `knowledge-persistence.md`, which is why the item lives there
rather than in a Serena memory, but binding means "every harness reads it", not
"a gate rejects a violation".

## Evidence for the rule's own claim

The item asserts a failure mode measured twice in PR #5176, and the rule text
carries both measurements inline: the exact expressions, the tier the case ran,
and what each edit did or failed to do. That is deliberate, so the binding claim
stands on its own and does not depend on a file the reader may not have.

The fuller write-ups were on PR #5176's branch, which is why an earlier version
of this section named them as *contents of that PR* rather than as paths: if
this PR had merged first they would not have existed on `main` yet. Copilot
flagged the earlier wording for exactly that reason, and raised the sequencing
question that follows from it.

**Events answered that question.** PR #5176 merged to `main` at 2026-08-21
06:03:28 UTC as `15f95d2b6`, and `origin/main` is merged into this branch, so
the referenced artifacts now resolve here:

- `tests/commands/pr_autofix_dispatch_harness.py`
- `tests/commands/test_pr_autofix_tier_dispatch_runtime.py`
- `.agents/qa/session-99923-pr-autofix-tier-field-contract.md`
- `.agents/retrospective/2026-08-21-pr-5176-fixing-silent-failures-silently.md`

The claim is therefore no longer quoted from another branch. It is checkable
here, and was checked rather than assumed:

| Command | Result |
|---|---|
| `uv run --frozen python -m pytest tests/commands/test_pr_autofix_earned_t1_exemption.py::test_the_inverted_control_can_fail -q` | 2 passed |
| `uv run --frozen python -m pytest tests/commands/ -q` | 481 passed, 1 skipped |

An earlier version of this table wrote those as bare `pytest`. That is not the
command that ran, and the difference matters rather than being pedantic: bare
`pytest` resolves the ambient interpreter while `uv run --frozen` resolves the
locked environment, so the two can disagree about which dependencies exist.
`AGENTS.md` specifies the `uv run` form. Recording a command you did not run is
the same defect class this rule is about, one level up. Copilot found it.

The first is the executable form of the very failure this rule describes: it
asserts that the inverted control's discrimination probe can fail, so a probe
that measures nothing is exposed instead of quietly passing. Its passing on this
branch is the measurement the rule cites, run here rather than quoted.

### The second measurement, run rather than quoted

The rule's other instance is the comment-skip guard whose test used prose that
merely mentioned the syntax the guard rejects. Running a suite does not test
that: the guard is present, so the case passes either way. The measurement is a
mutation, so it was run as one.

Mutation: delete the comment skip in `contract_violations`
(`tests/commands/pr_autofix_field_parser.py`), the two lines reading
`if line.lstrip().startswith("#"): continue` before the
`unsupported_path_syntax` scan.

| Step | Command | Result |
|---|---|---|
| Guard removed | `uv run --frozen python -m pytest tests/commands/test_pr_autofix_field_contract.py -q -k comment` | 1 failed, 2 passed |
| Guard restored | same | 3 passed |

**DEAD, which is the required outcome for a discrimination probe.** The case
that failed is `test_bracket_notation_in_a_comment_is_not_a_violation`, and it
failed on the comment's own line, reporting the bracket-notation program
`.Tier // .["tier"]` as unreadable by the path extractor. The other two comment
cases passed with the defect present, which is the point restated as a
measurement.

The half the rule actually turns on was checked separately, because a passing
mutation proves the fixed test discriminates and says nothing about why the
original did not. With the guard still removed, calling `contract_violations`
directly:

| Comment body | Violations |
|---|---|
| prose mentioning the bracket form, no quoted jq program | `[]` |
| a real `jq -r '...'` invocation inside the comment | 1 |

So a comment of the first shape is invisible to the check even with the guard
gone: deleting the guard under test changes nothing, and the case passes having
measured nothing. That is the SURVIVED-is-a-finding shape, observed here rather
than quoted. Stated at the level actually measured: the original test's exact
prose is recorded on PR #5176, and what was reproduced here is the mechanism it
tripped over, not that specific string.

Restore verified byte-identical with `cmp -s` against a copy taken before the
edit, and `__pycache__` under `tests/commands/` cleared between the mutation and
the rerun, per `testing.md` SHOULD 8.

The rule text still carries both measurements inline (the exact expressions, the
tier the case ran, what each edit did or failed to do), and that stays
deliberate: `.claude/rules/canonical-source-mirror.md` covers the general case
under "True when you wrote it is not true at merge", and a rule outlives the PR
that motivated it. The inline detail is what keeps the binding claim readable
without the harness; the merge is what makes it reproducible with one.
