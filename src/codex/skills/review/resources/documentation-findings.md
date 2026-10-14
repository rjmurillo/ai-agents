# Documentation findings (local axis 2)

Local axis 2 composes `doc-accuracy`. `/review` keeps no accuracy checklist of
its own (issue #5398).

1. **Select.** `select_axes.py` puts `doc-accuracy` in `local_selected` for a
   docs or instruction path. A code-only diff can still make a durable claim
   stale, so also run the `test` skill's `doc_accuracy_trigger.py` on the
   three-dot diff: every changed path as its own argument, each effect you
   verified, and `--build-record <doc-impact-path>` when `/build` handed one
   over. On `"decision": "activate"`, run local axis 2 even when
   `local_selected` omits it. On `"skip"`, quote the `reason` in the Selection
   cell.
2. **Reuse.** A `DOC ACCURACY REPORT` from `/test` Gate 5 for this exact head
   stands in for the scan. A report for an older head is stale: run the axis. A
   `/review` invoked directly has no report, so it runs the trigger itself. A
   missing report is never a skip.
3. **Unrun.** An activated axis that did not run, or whose required phase did
   not run, is `UNKNOWN`. It is never `PASS`.
4. **Classify.** Add a `remediation` field to each finding, with one class. The
   `test` skill's `references/doc-accuracy-gate.md` owns the classes in its
   Report block; prefer the ones that remove a representation.

| Finding | Remediation |
|---------|-------------|
| Required claim the code contradicts | correct durable claim, then verify it against the canonical source |
| Derived mutable fact, such as a count or a list | delete derived claim, or reference canonical source |
| One claim authored in two places | consolidate authority |
| Generated copy differs from its input | generate projection; fix the canonical source, never the copy |
| Dated measurement in a retrospective, changelog, or archive | historical evidence: report as info and leave it out of the verdict |
