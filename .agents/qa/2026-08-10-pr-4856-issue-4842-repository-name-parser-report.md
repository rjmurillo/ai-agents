---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-14653-issue-4842-repository-name-dots.json
qaCommit: 42f83d67cedb87e4fe0dd27e9ea4b63f84185810
---

# Issue 4842 QA

Priority is P1. The defect breaks every inferred GitHub operation for
repositories whose names contain dots. The one-line parser fix is merited.

## Evidence

- Reproduction returned `RepoInfo(owner='rjmurillo', repo='moq')` for
  `moq.analyzers.git`.
- `tests/test_github_core.py` passed 251 tests.
- The regression test failed all 3 dotted-name cases with the defect restored.
- The lookalike-host tests failed 2 cases with the unanchored pattern restored.
- Ruff passed on the canonical source and test file.
- Security scan found 0 CWE-78 findings in 2 files.
- Plugin library mirror check passed.
- Re-run on the merge commit that brought in current main: `tests/test_github_core.py`
  passed 251 tests and Ruff passed on the canonical source, both plugin mirrors, and
  the test file.

The file-level quality scorer reported the existing 829-line module below its
cohesion threshold. This change adds no function, branch, or dependency.
