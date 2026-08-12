---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-10037.json
qaCommit: ce3641d1084338690a381587c4117f34d9d96e69
---

# PR 4758 always-on re-measurement validation

## Result

PASS. Both red required checks have a reproduced root cause and a fix
verified against the gate that failed. The 13 assertions the main merge
broke now pass, and no gate that passed before this session fails after it.

## What was broken

`Validate PR` failed inside `scripts/ci/check_pr_qa_report.py` with
`No QA report found for code changes`. The PR edits
`scripts/validation/instruction_budget_constants.py` and
`tests/validation/test_instruction_budget.py`, both `.py`, so the gate was
correct and the branch was missing evidence. This report and its session log
are that evidence.

`Run Python Tests` failed inside `scripts/ci/ruff_count_ratchet.py`:

```text
ruff count ratchet: BASELINE ABOVE BASE. This tree records 43, FETCH_HEAD
records 30 (+13). The measured count is 27, which FETCH_HEAD already allows,
so nothing in this tree added a violation.
```

The branch was 35 commits behind `main` and carried the older, higher
baseline. Merging `main` as `221a36fccf` picked up the lowered value.

## What the merge then broke

Merging `main` restored three prose documents to their pre-rescope figures,
which `main` had re-measured with `lsp-first` still always-on. 13 assertions
that pass on `main` failed on the merged branch:

- 12 in `tests/validation/test_always_on_corpus_claims.py` (doctrine table,
  always-on figures, `.py` figures, source basis, plugin tree, 8KB
  multipliers, and both non-doctrine prose documents).
- `test_real_repo_python_baseline_is_under_ceiling_and_nonzero` at 99,411
  bytes against the 99,000 ceiling.

## Fixes

The `.py` breach is this PR's own doing. `main` measures 98,974 bytes with 26
bytes of headroom, and the rescope added 437: a 155-character `applyTo` glob
list plus a new Scope section. Raising the ceiling was rejected, because
`instruction_budget_constants.py` ratchets down and this PR already lowers
`.md` from 84,000 to 83,000. The prose was trimmed instead: the ADR-062
history paragraph compressed, the Scope section folded into it, and the
References restatement of the same amendment cut. The mirror fell from 3,411
to 2,951 bytes and the `.py` corpus to 98,951.

Every figure below is a live measurement taken with
`tests/validation/always_on_corpus_helpers.py`, the same helpers the failing
tests call.

| Figure | Before | After |
|---|---|---|
| Always-on rules, both trees | 8 rules, 73,223 bytes | 7 rules, 70,249 bytes |
| Always-on at `.claude/rules/` | 73,358 bytes, 135 delta | 70,365 bytes, 116 delta |
| `.py` effective context | 98,974 bytes, 11 files | 98,951 bytes, 11 files |
| 8KB multipliers | 9.0x always-on, 12.1x Python | 8.6x always-on, 12.1x Python |
| Book-derived always-on share | 19.3% | 20.1% |

One first-pass error was caught before it shipped. Shrinking
`canonical-source-mirror.md` does not shrink the always-on corpus, because
that rule is path-scoped rather than always-on. The measured figures stayed
70,249 and 70,365, and the document was corrected against the measurement
rather than against the arithmetic.

## Evidence

- Targeted tests at `ce3641d10`: 144 passed across
  `tests/validation/test_always_on_corpus_claims.py`,
  `tests/validation/test_audit_procedure_claims.py`, and
  `tests/validation/test_instruction_budget.py`. Same three files on `main`:
  57 and 86 passed, which is the baseline this branch had to return to.
- Negative control: the same three suites on a detached `origin/main`
  worktree pass, and failed 13 assertions on the merged branch before the
  fix. The tests therefore discriminate; they are not passing vacuously.
- `scripts/ci/ruff_count_ratchet.py --base-ref origin/main`: OK, 27
  violations against baseline 30.
- `scripts/ci/taste_count_ratchet.py --base-ref origin/main`: OK, count
  equals baseline 583.
- `scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main`: OK,
  count equals baseline 44.
- `build/scripts/build_all.py --check`: no drift. Both instruction trees and
  `src/copilot-cli/skills/context-optimizer/references/` were regenerated
  from their canonical sources, never hand-edited.
- `npx markdownlint-cli2` on the four edited Markdown sources: 0 issues.
- `taste_lints.py` on the same four files: 0 errors, 1 pre-existing size
  warning on `model-context-doctrine.md` at 325 of 500 lines.
- `scripts/update_memory_index_tokens.py` regenerated the one changed token
  count (2162 to 2157).

## Scope not covered

The full pytest suite was not run in this session; the pre-push hook runs it
and gates the push. The `.md` ceiling at 83,000 against a measured 70,249 is
left as this PR set it, because narrowing it further is a different
ratchet decision than the one this PR makes.
