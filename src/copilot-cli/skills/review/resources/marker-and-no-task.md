# Review marker format and the no-Task path

`/review` loads this file when it writes the PASS marker, or when its harness has no `Task` tool. The reader is `.claude/skills/review/scripts/validate_review_marker.py` (`MARKER_TRAILER_KEY = "Reviewed-By"`, `ARTIFACT_TRAILER_KEY = "Review-Artifact"`).

## Why the marker carries a report

A bare trailer is a sentence anyone can type. A subagent that never ran the axes could write `git commit --allow-empty --trailer "Reviewed-By: ..."` and pass every gate. The report is the reviewer's artifact, and the `Review-Artifact` digest binds the marker to that exact text. The digest shows the report was not edited after the trailer was written and that a report exists to read. It does not prove who wrote the report. Reviewers of the branch can read the report in the marker commit body.

## Marker format

```text
--- review report ---
Reviewed-SHA: <reviewed-tip-sha>
<axis>: <VERDICT>
--- end review report ---

Reviewed-By: /review@<comma-separated-axis-list> on <reviewed-tip-sha>
Review-Artifact: sha256:<digest of the report lines>
```

The report has one `<axis>: <VERDICT>` row per axis in the axis list. The verdict comes from that axis's `extract_verdict` result: `PASS`, or an acknowledged `WARN`. The validator rejects a report with a missing, extra, or failing row, a report that names another SHA, and a digest that does not match.

## Write steps

A commit cannot name its own SHA in a trailer (the SHA hashes the trailer, so writing the SHA changes the SHA, with no fixed point). Record the reviewed tip, then write an empty marker commit on top of it.

1. `REVIEWED_TIP=$(git rev-parse HEAD)` (the code that was reviewed).
2. Build the axis list from the axes that ran (comma-separated stems, e.g. `analyst,architect,qa,security,...`).
3. Write `report.txt` with the report block above: `Reviewed-SHA: $REVIEWED_TIP` and one row per axis from its extracted verdict. Never write a row for an axis that did not run.
4. `DIGEST=$(python3 <validate_review_marker.py> --digest report.txt)`
5. Write `marker-message.txt`: the subject `review: /review PASS marker`, a blank line, the contents of `report.txt`, a blank line, then the `Reviewed-By` and `Review-Artifact: $DIGEST` trailers.
6. `git commit --allow-empty -F marker-message.txt`

## Running without the Task tool

A subagent with no `Task` tool MUST NOT review its own diff and write the marker. Run each axis as its own `claude -p` process, so the reviewer has the axis prompt and nothing from the authoring session.

```bash
# <axis-prompt> is the resolved references/{role}.md; context.txt starts with the CONTEXT_MODE line, then the diff.
claude -p --system-prompt-file "<axis-prompt>" --allowedTools "Read Grep Glob" < context.txt > "axis-{role}.out"
```

Run the Stage-1 `spec-compliance` axis first, then the step 4 selection, then step 4c, one process each. Extract each verdict with `extract_verdict` exactly as in step 6, and keep every `axis-{role}.out` file as the evidence behind the report. If `claude` is not on `PATH`, record `UNKNOWN` for every axis: no verdict is a non-PASS verdict, and a non-PASS verdict writes no marker.
