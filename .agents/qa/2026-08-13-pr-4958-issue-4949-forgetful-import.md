---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14695-bb3e599a1-fix-issue-4949-forgetful-full-backup.json
qaCommit: dbf1449b54c87bb96828563ae621a83741a2a4ad
---

# QA Report: Issue 4949 Forgetful Import

## Scope

Validate that the committed January 19 Forgetful backup imports through its
legacy one-row and empty-table shapes, then allows later correction files to
run.

## Acceptance Results

| Behavior | Result | Evidence |
|----------|--------|----------|
| One object becomes one row | PASS | Direct normalization test and committed backup test |
| Null becomes an empty table | PASS | Direct normalization test and committed backup fixture |
| Arrays remain row arrays | PASS | Direct array and empty-array tests |
| Malformed table value names its table | PASS | CLI diagnostic test |
| Malformed list row names table and index | PASS | Direct validation test |
| Malformed export root reports its file | PASS | Four parameterized CLI cases |
| Malformed data section reports its file | PASS | CLI continuation test |
| Later correction files still run | PASS | Backup, malformed-root, and malformed-data tests |
| Prior successful inserts remain counted | PASS | Malformed later-table regression test |

## Verification

- Focused importer suites: 41 passed.
- Full repository suite with canonical pytest parallelism: 27,941 passed and
  37 skipped.
- Committed backup against a temporary database copy: 2,359 inserted, exit 0.
- Mutation check: disabling object normalization failed the committed backup
  plus later correction test, and the source hash was restored.
- Scoped Ruff check and format check: passed.
- Taste lints: zero errors. Both touched files remain below 500 lines.
- CWE-78 scan: two Python files scanned, zero findings.
- Security agent: approved with no medium-or-higher finding.
- GPT-5.6 Sol final adversarial review: approved.
- Fresh QA review of commit `dbf1449b54c87bb96828563ae621a83741a2a4ad`
  after indexing the durable memory: PASS, no blocking defects.

## QA Verdict

PASS. The implementation and tests satisfy all issue acceptance criteria.
