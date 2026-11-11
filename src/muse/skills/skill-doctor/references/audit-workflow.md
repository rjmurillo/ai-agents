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

Set `session_id` to `<harness>:<id>`, the harness name and the session's `meta.id` from `inventory.json`, for example `copilot:3f2a9c`. Batched reviews assign the same form, and the report lists records by it.

```bash
python3 "$SKILL_ROOT/scripts/audit_scores.py" "$REPORT_DIR/scores.json" --out "$REPORT_DIR/score_artifact.json"
```

It exits 1 and writes nothing when a label does not match its rubric value, a reason is missing, or a session id repeats. Fix the scores and rerun.
When `terminated_by` is set, give every result an explicit `pre_cutoff`: `true` when the score rests on evidence from before the provider cutoff, `false` when it judges only the cut-off ending. A missing `pre_cutoff` on a terminated session counts as `false`, so that session leaves `failed_conversations`.

## Assemble report.json

Write a draft `report.json` with everything except the numbers: `title`, `generated_at`, `harness`, `handle`, `stats`, `sampling`, `top_findings`, `suggestions`, and `evaluation`. Then let the script fill the numbers from the scored records:

```bash
python3 "$SKILL_ROOT/scripts/assemble_report.py" "$REPORT_DIR/report.json" \
  --scores "$REPORT_DIR/scores.json" --artifact "$REPORT_DIR/score_artifact.json" \
  --manifest "$REPORT_DIR/audit_manifest.json" --out "$REPORT_DIR/report.json"
```

It recomputes the score artifact from `scores.json` and sets `scores`, `stats.sessions_analyzed`, each `sampling.per_harness.<harness>.overall`, and the `audit` object (`scores` and `records`, plus `catalog` from the manifest). Leave out `--manifest` when the collector ran without `--audit-manifest`. It drops `grade` so the renderer derives it. It exits 1 and writes nothing when the scores are invalid, a harness's `sampled` count differs from its scored sessions (import every batch first), `--artifact` does not match the recomputation, or the result fails the renderer's checks; it exits 2 on an unreadable file. Writing over the draft is safe: a failed run leaves it unchanged.

## Batched reviews

For a long review, split the work into batches instead of scoring in one pass:

```bash
python3 "$SKILL_ROOT/scripts/audit_batches.py" assign "$REPORT_DIR/inventory.json" --batch-size 20 --out "$REPORT_DIR/batches"
python3 "$SKILL_ROOT/scripts/audit_batches.py" import "$REPORT_DIR/batches/<batch file>" <rows.json> --accepted "$REPORT_DIR/scores.json"
```

Each score row carries its `batch_id` and `source_digest`. An import that has missing, extra, duplicate, malformed, or foreign rows, or a batch file stripped of its selection rule, counts, or non-probability note, exits 1 and leaves the accepted file unchanged. A changed inventory needs a new assignment.

## Report sections and export

`assemble_report.py` writes the `audit` object for local browsing. The renderer exits 1 when the scorecard and the artifact disagree, so a hand-edited score is caught.
`report.html` keeps paths and session ids for local use. To share results, run `python3 "$SKILL_ROOT/scripts/public_export.py" "$REPORT_DIR/report.json" --out <path>`; it writes aggregates only and exits 1 if any private value reaches the export.
