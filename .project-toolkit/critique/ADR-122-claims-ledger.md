# ADR-122 Claims Ledger

Evidence date: 2026-11-16.
Base revision: `5ac4f739ee088a2a50bea7395763c378d0d1ffd7` (2026-11-16).
The evidence below covers the working-tree admission implementation.
Decision items describe the selected policy, not additional historical claims.

| Claim | Kind | Command or source | Result |
|---|---|---|---|
| The maintainer required language tooling and authorized this dependency policy change. | quote | User instructions: "waiver, full send." The subsequent instruction explicitly selected the scoped policy change. | VERIFIED. This records an instruction, not GitHub approval. |
| The parser imports `tree_sitter` and `tree_sitter_c_sharp`. | behavior | Read `_count_csharp_imports` in `src/claude/skills/code-qualities-assessment/scripts/assess.py`. | VERIFIED. The function imports the grammar and Tree-sitter API lazily. |
| Those dependencies lower coupling from 10.0 to 8.0. | behavior | Run the scanner against `origin/main`, targeting its canonical script, with JSON output. | VERIFIED. On 2026-11-16, the report records 23 imports: 21 standard-library and 2 scored. |
| Without admission, this transition exits 10. | behavior | Control: copy `.qualityrc.json` with the `csharpParserDependencyAdmission` key removed, then run `uv run --frozen python src/claude/skills/code-qualities-assessment/scripts/assess.py --target src/claude/skills/code-qualities-assessment/scripts/assess.py --changed-only --base origin/main --config <copy> --format json --output <report>`. | VERIFIED. Exit 10, rerun on 2026-11-18. Stderr retains `coupling regressed 10.0 -> 8.0 (delta -2.0)`. With the real `.qualityrc.json` the same command exits 0. |
| The exact admission exits 0 without removing the raw regression. | behavior | Run the previous scanner command with `.qualityrc.json` instead of the control configuration. | VERIFIED. Exit 0. JSON retains `regressions: ["coupling"]`. Stderr prints the original failure and `ADMITTED`. |
| Configuration cannot widen the authorized scope. | behavior | Use the full regression-suite command below, which includes `test_parser_admission.py`. Read `_apply_csharp_parser_dependency_admission`. | VERIFIED. Missing authorization, changed scope, and malformed records fail. Python AST checks actual external import roots. |
| Other regressions, lost evidence, and new-file threshold failures remain blocking. | behavior | `uv run --frozen --extra dev pytest tests/skills/code-qualities-assessment/test_assess.py tests/skills/code-qualities-assessment/test_csharp_coupling.py tests/skills/code-qualities-assessment/test_parser_admission.py tests/test_assess_regression.py tests/test_verdict.py --cov=scripts.ai_review_common.verdict --cov-branch --cov-report=term-missing -q --tb=short` | VERIFIED. On 2026-11-18, 555 tests passed at commit 373eb5ce0. Controls assert actual CLI return codes. |
| The adapter emits `WARN` for valid admitted evidence, not `PASS`. | behavior | `uv run --frozen --extra dev pytest tests/test_verdict.py -q --tb=short`. The scanner admission test also passes real JSON to the adapter. | VERIFIED. On 2026-11-18, 223 adapter tests passed (measured at commit 373eb5ce0). Invalid records cannot become `PASS`. Exits 10 and 11 remain `FAIL`. |
| The prior adapter revision is `9b135a94dab9c4863252eb9a1c779f281643d899` (2026-10-18). | path | `git log -1 --format="%H %cs %s" origin/main -- scripts/ai_review_common/verdict.py` | VERIFIED. The command returned that commit and date. |
| Commit `ede8a576fa19e2bd53b9602d7fe9d4ea2b53b46d` (2026-11-15) excluded Python stdlib imports. | behavior | `git log -1 --format="%H %cs %s" origin/main -- src/claude/skills/code-qualities-assessment/scripts/assess.py` and `_score_coupling` source. | VERIFIED. The title identifies the stdlib exclusion, and the scoring code excludes those imports. |
| Removing the record restores ordinary rejection. | behavior | Compare the actual scanner runs with and without the configuration record. | VERIFIED. Exits differ from 0 to 10, with identical raw coupling values. |

## Documentation Accuracy

VERIFIED. Phase 4 compared ADR behavior claims with the scanner and adapter.
The source retains the regression before marking its admission.
The CLI applies the admission before rendering and gating.
The adapter checks admitted scope and keeps nonzero failure exits blocking.
No claim equates maintainer authorization with a human review approval.

## Self-Consistency

VERIFIED. The decision preserves raw evidence while changing policy admission.
Exit 0 describes policy satisfaction, not absence of a raw regression.
`WARN` preserves that distinction for review.
The rollback consequence follows the measured no-admission control.
The dependency-specific exception does not alter another quality or repository policy.

## Refuting Seat

The analyst seat found no factual contradiction in the inspected behavior.
Its complete-verification result was `UNAVAILABLE`, not `VERIFIED`.
Its GitHub history request returned 404; it did not rerun processes.
Local Git subsequently confirmed both historical commits, dates, and commit messages.
The original terminal executions returned exits 0 and 10 respectively.
The seat's access limitation does not contradict those observed process results.
Seat cost, model, and wall time are unavailable from its returned receipt.
The seat reported no factual findings requiring a writer correction.

## Final Scoped Validation

On 2026-11-18, the final parser and policy suite passed 555 tests. The count was measured at commit 373eb5ce0 with the command below. Later commits on the pull request add tests, so the count at the final head is higher.
The command covered the scanner, C# parser, regression controls, and verdict adapter.

Command: `uv run --frozen --extra dev pytest tests/skills/code-qualities-assessment/test_assess.py tests/skills/code-qualities-assessment/test_csharp_coupling.py tests/skills/code-qualities-assessment/test_parser_admission.py tests/test_assess_regression.py tests/test_verdict.py -q --tb=short`.

The full pre-PR run found a redundant admission branch and unspecified subprocess encodings.
Removing the redundant condition restored the canonical scanner's existing complexity bound.
Both subprocess captures now explicitly select UTF-8 and replacement decoding.
Direct working-tree checks report zero complexity violations and zero I/O portability violations.
Canonical generation completed again with exit 0.
Normal independent review and protected CI remain separate requirements.

## Item 10 (2026-11-20, issue #7493)

Evidence date: 2026-11-20. Rows were rerun at branch head `80f5ca22c` (2026-11-20), after the panel's round-1 fixes. That head merges `origin/main` at `bdcae2eaa` (2026-11-20).

| Claim | Kind | Command or source | Result |
|---|---|---|---|
| The maintainer authorized the waiver in decisions D1 and D2, choice A each. | quote | Issue #7493 comment 7050456436 (https://github.com/rjmurillo/ai-agents/issues/7493#issuecomment-7050456436) quotes both choices. | VERIFIED. The comment records the session decisions. It is not a GitHub review approval. |
| Eight comparable scores dropped by more than 0.5 on this change. | behavior | Control: copy `.qualityrc.json` without `changeAdmissions`, then `uv run --frozen python .claude/skills/code-qualities-assessment/scripts/assess.py --target . --changed-only --base origin/main --config <copy> --format json`. | VERIFIED. Exit 10. Stderr lists exactly the eight transitions in the item 10 table and no `ADMITTED` line. |
| The exact records admit all eight and keep the raw evidence. | behavior | The same command with the real `.qualityrc.json`. | VERIFIED. Exit 0. Each of the eight regression lines prints, each followed by one `ADMITTED: issue #7493` line. JSON keeps `regressions` and adds `change_admissions`. |
| Configuration cannot widen the records. | behavior | Copy `.qualityrc.json`, change the first record's `headBlob` to forty zeros, rerun with `--config <copy>`. | VERIFIED. Exit 1 with `ERROR: Invalid changeAdmissions: scope or authorization differs`. `test_change_admission.py` covers field, order, and partial-match cases. |
| The review adapter reports `WARN` for the admitted run, never `PASS`. | behavior | `adapt_local_axis_verdict("code-qualities-assessment", <scanner JSON>, 0)` from `.claude/lib/ai_review_common/verdict.py`. | VERIFIED. Returns `WARN`. `test_verdict_change_admission.py` covers `UNKNOWN` for tampered, mismatched, and mixed records, and `FAIL` on exit 10. |
| The scanner and adapter changes do not regress their own scores. | behavior | The admitted scanner run above, then `grep -E "assess.py|verdict.py" <stderr>` on its output. | VERIFIED. No regression line names `assess.py` or `verdict.py`. Neither file gained an import; both sat at the cohesion floor of 1.0 before the change. |
| The three record copies are equal. | behavior | `uv run --frozen pytest tests/test_verdict_change_admission.py -k "conformance or same_list" -q`. Both tests call one `_copies_agree` helper; the control drifts one blob and expects it to fail. | VERIFIED. Passes; the control fails on a drifted adapter copy. |
| Coupling 6.0 to 3.0 is the largest drop any ADR-122 record admits. | count | `uv run --frozen python -c` that loads `assess.py` and prints `max(b - h)` over `_PARSER_DEPENDENCY_ADMISSIONS` and `_CHANGE_ADMISSIONS` scores. | VERIFIED. The largest prior drop is 2.0. |
| An added symlink to a directory is skipped with a stderr line; a type change is not. | behavior | `test_an_added_directory_link_is_skipped_with_a_stderr_line` and `test_a_type_change_to_a_directory_link_still_reaches_scoring` in `test_change_admission_blobs.py`. The real scan prints `SKIPPED (directory): .claude/lib/memory_enhancement`. | VERIFIED. Before the skip, that link scored `scoring_failed: true` and the adapter returned `UNKNOWN`. |
| The record paths are plain literals with a documented baseline entry. | behavior | `uv run --frozen python scripts/validation/check_vendor_portability.py` and the comment above the `assess.py` entry in `scripts/validation/vendor_portability_baseline.txt`. | VERIFIED. Exit 0. |
| Records pin scores and blobs, not import sets. | behavior | `grep -n "imports" ` over `_change_admission_mismatch` in `assess.py` finds nothing; `test_a_same_score_edit_with_other_content_stays_blocking_end_to_end` exercises the blob check. | VERIFIED. Matching compares change status, absolute-gate reason, evidence loss, the quality's base, head, delta, and status, and both blob ids. No import set is read. |
| Without the `changeAdmissions` key, no record applies. | behavior | `_apply_change_admissions` returns before matching when the key is absent; `test_change_admission.py` pins it. | VERIFIED. |
| A scan that assesses no file exits 0 before admissions are read. | behavior | `main` in `assess.py` returns 0 for an empty regression run before `_apply_change_admissions`. | VERIFIED. This predates item 10 and applies to the parser records too. On that path a tampered `changeAdmissions` is never validated. No comparison exists, so nothing is admitted. |
| A branch whose base predates a later change to these files matches no record. | behavior | The matching rule requires the record's exact base score; a later change to the file on main moves the base score. | INFERRED from the matching rule. Not observed. |
| The eight records name six distinct files. | count | Read the item 10 table and `_CHANGE_ADMISSIONS` in `assess.py`. | VERIFIED. Two files carry two records each. None is the scanner. |
| Records go inactive once these files merge. | behavior | Item 2 matching requires the exact base score; after merge the base holds the head score. | INFERRED from the matching rule. Not observed, because the change has not merged. |
| Each record pins the base and head blob ids, and all eight match git. | behavior | For each record: `git rev-parse --verify --quiet --end-of-options origin/main:<file>` and `git hash-object -- <file>`. | VERIFIED. 8 of 8 match at `80f5ca22c`. |
| An edit that keeps both scores still voids a record. | behavior | `test_a_same_score_edit_with_other_content_stays_blocking_end_to_end` in `test_change_admission_blobs.py` builds the pinned 8.0 to 7.0 scores with other content and restores the real blob lookup. | VERIFIED. Exit 10 with `NOT ADMITTED` and `differs from the pinned blobs`. |
| The base blob lookup returns only the object id. | behavior | `test_blob_ids_reads_git_for_base_and_working_tree`. | VERIFIED. It caught `rev-parse --end-of-options` echoing that option as an output line; the scanner now passes `--verify --quiet`. |
| The admission and adapter suites pass. | behavior | `uv run --frozen pytest tests/skills/code-qualities-assessment/test_change_admission.py tests/skills/code-qualities-assessment/test_change_admission_blobs.py tests/test_verdict_change_admission.py tests/skills/code-qualities-assessment/test_parser_admission.py tests/test_verdict.py -q` | VERIFIED. 372 passed at `80f5ca22c`. |

### Item 10 documentation accuracy

VERIFIED for every behavior sentence in item 10, each mapped to a row above. The provenance sentences (security fixes added the code; D2 widened D1 after three more drops) rest on the session decisions recorded in the issue #7493 comment, not on a command. The stale-base sentence is INFERRED from the matching rule.

### Item 10 self-consistency

VERIFIED with one stated conflict. Item 5 says not to extend admission to another repository or another quality. Item 10 admits another quality, and it also admits files other than the scanner, which item 2 had limited to the scanner. It says so, on the maintainer's decision, and admits nothing beyond its eight records. The Rationale table rejects a generic framework; item 10 keeps fixed in-code records, so that rejection still holds.

## Item 10 pin renewal (2026-11-22, issue #7493)

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| Decision D5 renews two search pins. | Quote | Read issue #7493 comment 7086682234. | VERIFIED. The receipt names the exact replacement blob and both scores. |
| All eight admissions still match file content. | Behavior | Run `git rev-parse origin/main:<file>` and `git hash-object -- <file>` for each record. | VERIFIED. Every base and head blob matches. |
| The assessor retains every regression and reports the new receipt. | Behavior | Run `assess.py --target . --changed-only --base origin/main --format json`. | VERIFIED. Exit zero with eight raw drops and eight admissions. Two admissions cite the D5 receipt. |
| The renewal preserves fail-closed behavior. | Behavior | Remove `changeAdmissions` from a temporary config and rerun the assessor. | VERIFIED. Exit 10 with all eight drops. The adapter reports FAIL. |
