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
| Without admission, this transition exits 10. | behavior | `uv run --frozen python src\claude\skills\code-qualities-assessment\scripts\assess.py --target src\claude\skills\code-qualities-assessment\scripts\assess.py --changed-only --base origin/main --config .project-toolkit\scratch\7406-quality-without-admission.json --format json --output .project-toolkit\scratch\7406-unadmitted-quality.json` | VERIFIED. Exit 10. Stderr retains `coupling regressed 10.0 -> 8.0 (delta -2.0)`. |
| The exact admission exits 0 without removing the raw regression. | behavior | Run the previous scanner command with `.qualityrc.json` instead of the control configuration. | VERIFIED. Exit 0. JSON retains `regressions: ["coupling"]`. Stderr prints the original failure and `ADMITTED`. |
| Configuration cannot widen the authorized scope. | behavior | Use the full regression-suite command below. Read `_apply_csharp_parser_dependency_admission`. | VERIFIED. Missing authorization, changed scope, and malformed records fail. Python AST checks actual external import roots. |
| Other regressions, lost evidence, and new-file threshold failures remain blocking. | behavior | `uv run --frozen --extra dev pytest tests\skills\code-qualities-assessment\test_assess.py tests\skills\code-qualities-assessment\test_csharp_coupling.py tests\test_assess_regression.py tests\test_verdict.py --cov=scripts.ai_review_common.verdict --cov-branch --cov-report=term-missing -q --tb=short` | VERIFIED. On 2026-11-16, 545 tests passed. Controls assert actual CLI return codes. |
| The adapter emits `WARN` for valid admitted evidence, not `PASS`. | behavior | `uv run --frozen --extra dev pytest tests\test_verdict.py -q --tb=short`. The scanner admission test also passes real JSON to the adapter. | VERIFIED. On 2026-11-16, 223 adapter tests passed. Invalid records cannot become `PASS`. Exits 10 and 11 remain `FAIL`. |
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
The receipt is `.project-toolkit/scratch/7406-admission-history-proof.txt`.
The original terminal executions returned exits 0 and 10 respectively.
The seat's access limitation does not contradict those observed process results.
Seat cost, model, and wall time are unavailable from its returned receipt.
The seat reported no factual findings requiring a writer correction.

## Final Scoped Validation

On 2026-11-16, the final parser and policy suite passed 547 tests.
The command covered the scanner, C# parser, regression controls, and verdict adapter.

Command: `uv run --frozen --extra dev pytest tests\skills\code-qualities-assessment\test_assess.py tests\skills\code-qualities-assessment\test_csharp_coupling.py tests\test_assess_regression.py tests\test_verdict.py -q --tb=short`.

The full pre-PR run found a redundant admission branch and unspecified subprocess encodings.
Removing the redundant condition restored the canonical scanner's existing complexity bound.
Both subprocess captures now explicitly select UTF-8 and replacement decoding.
Direct working-tree checks report zero complexity violations and zero I/O portability violations.
Canonical generation completed again with exit 0.
Normal independent review and protected CI remain separate requirements.
