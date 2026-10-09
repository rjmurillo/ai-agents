# Execution Plan: Balance xdist loadfile workers by splitting slow test files

## Metadata

| Field | Value |
|-------|-------|
| **Status** | Completed |
| **Created** | 2026-10-08 |
| **Owner** | claude |
| **Complexity** | Low |

## Objectives

- [x] M1: `tests/test_validation_pre_pr.py` runs in under 5s alone. Its slow classes move to files that each run in under 30s.
- [x] M2: The vendor-portability real-checker test runs in two files. Neither takes 30s or more. A guard proves the two lists together cover every validator.
- [x] M3: The same test count and test names before and after. Traced 16-worker tail below the 35.5s baseline, posted on #6211.

## Milestones and tasks

### M1: Split `tests/test_validation_pre_pr.py` (ships alone)

Exit: AC 1, 2, 3, 8 hold for this file and its new files.

| Task | Size | Done when |
|---|---|---|
| T1.1 Move `_sequence_with_passing_corpus_gates`, `_sequence_with_failing_python_syntax`, `_healthy_git_run` to `tests/validation/pre_pr_main_helpers.py` | S | Helpers import cleanly and nothing else in the old file uses them |
| T1.2 Move `TestMain` to `tests/validation/test_pre_pr_main.py` | S | Its 2 tests pass alone |
| T1.3 Move the banner-shown tests of `TestHookModeBanner` to `tests/validation/test_pre_pr_banner_shown.py` | S | Tests pass alone, under 30s |
| T1.4 Move the banner-suppressed tests of `TestHookModeBanner` to `tests/validation/test_pre_pr_banner_suppressed.py` | S | Tests pass alone, under 30s |
| T1.5 Remove the moved code and unused imports from the old file | S | Old file passes alone in under 5s, ruff clean |

### M2: Split the vendor-portability real-checker test (ships alone)

Exit: AC 3, 4, 5, 8 hold.

| Task | Size | Done when |
|---|---|---|
| T2.1 Move the shared lookups (`_EXPECTED`, `_validator`, `_defining_module`, and what they need) to `tests/validation/vendor_portability_gate_helpers.py` | M | Original file imports them and still passes |
| T2.2 Add `tests/validation/test_pre_pr_vendor_portability_real_checker.py` for every validator except `validate_skill_md_portability`, plus the partition guard | S | Passes alone, under 30s. Guard fails when a validator is missing or appears twice |
| T2.3 Add `tests/validation/test_pre_pr_vendor_portability_real_checker_skill_md.py` for `validate_skill_md_portability` alone | S | Passes alone, about 26s |
| T2.4 Remove the real-checker test from the original file | S | Original file passes alone, well under 30s |

### M3: Verify and measure

Exit: AC 1, 6, 7.

| Task | Size | Done when |
|---|---|---|
| T3.1 Compare collected test names (module path stripped) and the count before and after | S | Identical sets |
| T3.2 Re-run the traced 832-file subset at 16 workers with the new file list | S | Tail and wall time recorded |
| T3.3 Post the before and after numbers on #6211 | S | Comment posted |

## Dependency graph

- T1.1 blocks T1.2 to T1.5. T2.1 blocks T2.2 to T2.4.
- M1 and M2 are independent and can run in either order.
- M3 needs M1 and M2.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A moved test stops running | Low | High | T3.1 compares test names and count |
| `patch("pre_pr_sequence._SEQUENCE")` targets resolve differently from a new module | Low | Medium | The patch targets are module strings, not relative to the test file. Run each file alone and under xdist |
| A new validator added to `_EXPECTED` later skips the real-checker test | Medium | High | The partition guard derives the fast list from `_EXPECTED` minus the slow one, so new validators land in the fast file automatically |
| Copied `noqa` comments trip the pre-push security suppression policy (#4352) | Medium | Low | Copy no `noqa` comments |
| Import-graph selection misses the new files | Low | Medium | New files import the same production modules. Check with `select_tests.select` on `scripts/validation/pre_pr.py` (Note 2026-10-09: PR #6241 retired the import-graph selector, so `select_tests` no longer exists and this risk no longer applies.) |
| Tail barely moves because 26s single tests remain | Medium | Low | Expected. Record what still limits it on #6211, as its acceptance criteria allow |

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-10-07 | Keep `--dist loadfile`, split slow files | Owner decision D2. Keeps module isolation | `--dist worksteal` or `load` |
| 2026-10-08 | Split `TestHookModeBanner` into banner-shown and banner-suppressed files | At 29.6s alone it sits at the 30s limit, and load inflates it | One file per class |
| 2026-10-08 | Keep the `pre_pr_sequence` import in `vendor_portability_gate_helpers.py` and test selection for each checker script | A selection replay found the split real-checker files were no longer picked when a checker script changed. On main the original file was picked through that import | Leave selection to the import graph alone |
| 2026-10-08 | Leave `test_run_pytest_windows.py` and `test_pre_pr_covers_workflow_validators.py` as they are | One 25.8s test, and a 13.4s module fixture. Splitting either cannot shorten the unit | Split them anyway |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-10-08 | Baseline measured and posted on #6211. Spec and plan written | claude |
| 2026-10-08 | M1 and M2 built. Selection regression found and fixed, AC9 added | claude |
| 2026-10-08 | M3 done. Paired runs: tail 36.5s to 37.9s on main, 28.8s to 29.4s on the branch. Posted on #6211 | claude |
| 2026-10-08 | Review round 1 findings fixed: spec wording, stale counts, guard checks each file's parametrize list | claude |

## Blockers

- None

## Related

- Issue: #6211
- Spec: `.project-toolkit/specs/SPEC-6211-balance-xdist-loadfile.md`
