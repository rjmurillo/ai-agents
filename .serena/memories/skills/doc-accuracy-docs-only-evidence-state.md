# Doc accuracy docs-only evidence state

Issue #4879 and PR #4956 establish the contract for Phase 3 compilability checks.

A target with zero source symbols has no source model for resolving documentation references. `.claude/skills/doc-accuracy/scripts/doc_accuracy.py` must return `DID_NOT_RUN`, emit zero compilability findings, include the reason `No source symbols found; Phase 3 cannot verify documentation references.`, and exit 1.

A target with source symbols still evaluates references. A real missing symbol remains a high finding, returns `FAIL`, and exits 10.

Evidence on 2026-08-13:

- Current `origin/main` scanned `.claude/rules`, found 27 docs and zero source symbols, emitted 14 high findings, returned `FAIL`, and exited 10.
- Commit `36cc0d87d86dac43c9068fda6ccc539786da7433` emitted zero findings, returned `DID_NOT_RUN`, and exited 1 for the same target.
- The positive, negative, and edge suite contains 88 passing tests in `tests/skills/doc-accuracy/test_doc_accuracy.py`.
- Restoring the original defect kills both new regression controls.

Use this state distinction when changing doc-accuracy reporting or build gate behavior. Inconclusive evidence must not be reported as proof that documentation is wrong.