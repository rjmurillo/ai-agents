# A pre-push job that pre_pr.py defers to must stay unscoped

A `pre_pr.py` gate can defer to a pre-push lefthook job through `already_run_by` (`scripts/validation/pre_pr_sequence.py:236` declares the field; the docstring at 227 explains it).

That lefthook job MUST stay unconditional. It must carry no `glob`, `files`, or `skip`.

A glob-skipped lefthook job looks the same as a pass. So `pre_pr.py` records the gate as passed with nothing run (issue #5317).

`tests/ci/test_lefthook_prepush_tiering.py:179` rejects a deferral target that carries `glob` (issue #5317). It does not check `files` or `skip`, so those stay a convention.

Scoping such a job never speeds the push. It drops coverage, or it moves the scan into `pre-pr-validation`. To cut push time, speed up the gate itself.

Evidence: issue #6734 slice 3 evaluated 16 unscoped pre-push jobs on 2026-10-23 and scoped none (comment 6363392164 on #6734).

No rule text carries this. The matching rule, `security.md`, covers a security category that needs asking first. Its F1 Instruction Bytes fixture had 8 bytes of headroom on 2026-10-23, so a rule item fails the gate.
