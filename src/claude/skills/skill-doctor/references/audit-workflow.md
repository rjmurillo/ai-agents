# Audit workflow

Scoring files, batched reviews, optional report sections, and the shareable export.
Every script here runs locally, writes atomically, and exits 0 on success, 1 on invalid input (writing nothing), and 2 on bad arguments or an unreadable file.

## scores.json

One record per scored session:

```json
{"sessions": [{"session_id": "", "harness": "", "skills_detected": true, "terminated_by": null,
  "scores": {"efficiency": {"label": "", "score": 0.0, "reason": "", "evidence_ref": "", "pre_cutoff": true},
             "code_quality": {}, "procedure_compliance": {}, "verbosity": {}}}]}
```

```bash
python3 "$SKILL_ROOT/scripts/audit_scores.py" "$REPORT_DIR/scores.json" --out "$REPORT_DIR/score_artifact.json"
```

It exits 1 and writes nothing when a label does not match its rubric value, a reason is missing, or a session id repeats. Fix the scores and rerun.
When `terminated_by` is set, give every result an explicit `pre_cutoff`: `true` when the score rests on evidence from before the provider cutoff, `false` when it judges only the cut-off ending. A missing `pre_cutoff` on a terminated session counts as `false`, so that session leaves `failed_conversations`.
Copy each `dimensions.<name>.score` and `overall` from `score_artifact.json` into `report.json`; use its `failed_conversations` and `per_harness` values.

## Batched reviews

For a long review, split the work into batches instead of scoring in one pass:

```bash
python3 "$SKILL_ROOT/scripts/audit_batches.py" assign "$REPORT_DIR/inventory.json" --batch-size 20 --out "$REPORT_DIR/batches"
python3 "$SKILL_ROOT/scripts/audit_batches.py" import "$REPORT_DIR/batches/<batch file>" <rows.json> --accepted "$REPORT_DIR/scores.json"
```

Each score row carries its `batch_id` and `source_digest`. An import that has missing, extra, duplicate, malformed, or foreign rows exits 1 and leaves the accepted file unchanged. A changed inventory needs a new assignment.

## Report sections and export

Optionally add an `audit` object for local browsing: `catalog` from `audit_manifest.json`, `scores` set to `score_artifact.json`, and `records` with the scored sessions. The renderer then exits 1 when the scorecard and the artifact disagree.
`report.html` keeps paths and session ids for local use. To share results, run `python3 "$SKILL_ROOT/scripts/public_export.py" "$REPORT_DIR/report.json" --out <path>`; it writes aggregates only and exits 1 if any private value reaches the export.
