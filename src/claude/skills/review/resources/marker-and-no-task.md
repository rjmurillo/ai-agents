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

The report has one `<axis>: <VERDICT>` row per axis in the axis list. The verdict is that axis's extracted token from SKILL.md Process step 6 (`extract_verdict`, or `adapt_local_axis_verdict` for the local axes `code-qualities-assessment`, `doc-accuracy`, `golden-principles`, and `taste-lints`). The validator accepts `PASS`, `COMPLIANT`, `PARTIAL`, and `WARN`; write `WARN` only when it was acknowledged. The validator rejects a report with a missing, extra, or failing row, a report that names another SHA, and a digest that does not match.

## Write steps

A commit cannot name its own SHA in a trailer (the SHA hashes the trailer, so writing the SHA changes the SHA, with no fixed point). Record the reviewed tip, then write an empty marker commit on top of it.

After the marker lands, you may merge `origin/main` into the branch without a new review. The validator and the security-review gate step over a merge commit when its second parent is on `origin/main` (change it with `--base-ref`) and its tree equals what `git merge-tree --write-tree` computes for its two parents. A merge that needed conflict edits, carries an extra edit, or pulls in another branch is new code: run `/review` again. Rebasing or amending rewrites the reviewed tip and always needs a new review.

1. `REVIEWED_TIP=$(git rev-parse HEAD)` (the code that was reviewed).
2. Build the axis list from the axes that ran (comma-separated stems, e.g. `analyst,architect,qa,security,...`).
3. Write `report.txt` with the lines from `--- review report ---` through `--- end review report ---`, delimiters included and no trailers (blank lines and trailing spaces inside the block are dropped before hashing): `Reviewed-SHA: $REVIEWED_TIP` and one row per axis from its extracted verdict. Never write a row for an axis that did not run.
4. `DIGEST=$(python3 <validate_review_marker.py> --digest report.txt)`
5. Write `marker-message.txt`: the subject `review: /review PASS marker`, a blank line, the contents of `report.txt`, a blank line, then the `Reviewed-By` and `Review-Artifact: $DIGEST` trailers.
6. `git commit --allow-empty -F marker-message.txt`

## Running without the Task tool

A subagent with no `Task` tool MUST NOT review its own diff and write the marker. Run each axis as its own `claude -p` process, so the reviewer has the axis prompt and nothing from the authoring session.

```bash
# <axis-prompt> is the resolved references/{role}.md, or resources/technical-review.md for the step 4c correctness pass; context.txt starts with the CONTEXT_MODE line, then the diff.
claude -p --system-prompt-file "<axis-prompt>" --allowedTools "Read Grep Glob" < context.txt > "axis-{role}.out"
```

Follow SKILL.md Process with these substitutions. Step 3, the complexity classifier, runs as its own `claude -p` process with the analyst prompt. Run the Stage-1 `spec-compliance` axis first, then the step 4 selection, then step 4c, one process each. Run `validate_findings_scope.py` on each `axis-{role}.out` as in step 4a before extracting its verdict, so an out-of-scope finding downgrades as it does on the Task path. The step 5 local axes run their scripts as written. Extract each verdict as in SKILL.md Process step 6, and keep every `axis-{role}.out` file as the evidence behind the report. If `claude` is not on `PATH`, record `UNKNOWN` for every axis: no verdict is a non-PASS verdict, and a non-PASS verdict writes no marker.
