# Claims Ledger: ADR-073 Amendment 2026-11-26

Each factual claim in the amendment, with the check that grounds it. Tree: branch `feat/7638-adr-review-by-ratchet` on `origin/main` at `ffc759356` (2026-11-26).

| Claim | Kind | Command | Result |
|---|---|---|---|
| 21 `proposed` records have no `review-by` | count | `uv run python scripts/validation/check_adr_lifecycle.py` | VERIFIED: `proposed-needs-review-by 21 / 21`. Analyst seat recounted 29 proposed records, 8 dated, 21 undated. |
| ADR-077 was the one past-due record | count | same run | VERIFIED: `review-by-past-due 1`, one line naming ADR-077 (due 2026-09-27). |
| ADR-077 sat in the baseline about two months | behavior | `git show origin/main:scripts/validation/adr_lifecycle_baseline.json` | VERIFIED: listed under `review-by-past-due`; ADR-073 records it entering on 2026-10-13. |
| `proposed-needs-review-by` exists and is ratcheted | behavior | read `CHECKS` and `ZERO_TOLERANCE_CHECKS` in `check_adr_lifecycle.py` | VERIFIED: in `CHECKS`, not in `ZERO_TOLERANCE_CHECKS`. |
| A malformed value stays a `review-by-format` finding | behavior | `test_a_proposed_record_with_a_malformed_date_is_only_a_format_finding` | VERIFIED: passes. |
| `--write-baseline` records past-due empty | behavior | `test_write_baseline_records_a_zero_tolerance_check_empty` | VERIFIED: passes. |
| A live baseline listing past-due is a config error | behavior | `test_a_past_due_record_fails_the_gate_and_the_baseline_cannot_hold_it` | VERIFIED: exit 2. |
| `review-by` optional except for `proposed` | behavior | `test_a_non_proposed_record_needs_no_review_by` | VERIFIED: passes for accepted, rejected, deprecated. |
| Templates default to a `YYYY-MM-DD` placeholder | path | `grep -n "review-by" .project-toolkit/architecture/ADR-TEMPLATE.md src/claude/skills/adr-generator/references/adr-template.md` | VERIFIED: both read `review-by: YYYY-MM-DD`. |
| `implemented-implies-decided` joins the set after #7636 | behavior | read `ZERO_TOLERANCE_CHECKS` after the rebase onto #7636 | Lands in the same PR after #7636 merges; this row is re-run then. |
