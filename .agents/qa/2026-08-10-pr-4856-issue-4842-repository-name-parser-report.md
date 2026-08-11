---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-14653.json
qaCommit: 78ca60b191b9ae71ada23b1b05694f9b6e1cc847
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

The file-level quality scorer reported the existing 829-line module below its
cohesion threshold. This change adds no function, branch, or dependency.
