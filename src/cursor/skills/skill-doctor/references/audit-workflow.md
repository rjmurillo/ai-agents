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
Set `thread` to the session's `thread` from `inventory.json`: `top_level` or `subagent`. A batch assignment carries it in `session_threads`, and the import fills it in for rows that leave it out. A row that names a different thread fails the import.

```bash
python3 "$SKILL_ROOT/scripts/audit_scores.py" "$REPORT_DIR/scores.json" --out "$REPORT_DIR/score_artifact.json"
```

It exits 1 and writes nothing when a label does not match its rubric value, a reason is missing, or a session id repeats. Fix the scores and rerun.
When `terminated_by` is set, give every result an explicit `pre_cutoff`: `true` when the score rests on evidence from before the provider cutoff, `false` when it judges only the cut-off ending. A missing `pre_cutoff` on a terminated session counts as `false`, so that session leaves `failed_conversations`.

## Aggregate formulas

Step 3 of `SKILL.md` runs `audit_scores.py`. These formulas define what it computes:

- `raw_efficiency` = mean of efficiency scores, excluding `insufficient_evidence` (0.5 if none, noted in findings).
- `raw_code_quality` = mean of code-quality scores, excluding `insufficient_evidence`. If no session had enough evidence, set it to 0.5 and say so in the findings.
- `raw_procedure_compliance` = mean of procedure-compliance scores, excluding `insufficient_evidence` (0.5 if none, noted in findings).
- `raw_verbosity` = mean of verbosity scores, excluding `insufficient_evidence` (0.5 if none, noted in findings).
- Curve qualitative rubric means into letter-grade report scores with `curve(score) = 0.5 + 0.5 * score`.
- `efficiency = curve(raw_efficiency)`.
- `code_quality = curve(raw_code_quality)`.
- `procedure_compliance = curve(raw_procedure_compliance)`.
- `verbosity = curve(raw_verbosity)`.
- `skill_coverage` = fraction of sampled sessions where at least one installed skill was detected. If `skills_found` is 0, coverage is 0.
- `overall = 0.25 * efficiency + 0.25 * code_quality + 0.2 * procedure_compliance + 0.15 * verbosity + 0.15 * skill_coverage.`

For each harness in `stats.per_harness` that has scored sessions, the script also computes that harness's `overall` by applying the formulas above to its sessions only. Report these next to the combined `overall`; they are never averaged back into it.
When records carry `thread`, the artifact also holds `per_thread` with each type's own `overall`, computed the same way.

## Assemble report.json

Write a draft `report.json` with everything except the numbers: `title`, `generated_at`, `harness`, `handle`, `stats`, `sampling`, `top_findings`, `suggestions`, and `evaluation`. Then let the script fill the numbers from the scored records:

```bash
python3 "$SKILL_ROOT/scripts/assemble_report.py" "$REPORT_DIR/report.json" \
  --scores "$REPORT_DIR/scores.json" --artifact "$REPORT_DIR/score_artifact.json" \
  --manifest "$REPORT_DIR/audit_manifest.json" --out "$REPORT_DIR/report.json"
```

It recomputes the score artifact from `scores.json` and sets `scores`, `stats.sessions_analyzed`, each `sampling.per_harness.<harness>.overall`, each `sampling.per_thread.<thread>.overall` when records carry `thread`, and the `audit` object (`scores` and `records`, plus `catalog` from the manifest). Leave out `--manifest` when the collector ran without `--audit-manifest`. It drops `grade` so the renderer derives it. It exits 1 and writes nothing when the scores are invalid, a harness's `sampled` count differs from its scored sessions (import every batch first), `--artifact` does not match the recomputation, or the result fails the renderer's checks; it exits 2 on an unreadable file. Writing over the draft is safe: a failed run leaves it unchanged.

## Batched reviews

For a long review, split the work into batches instead of scoring in one pass:

```bash
python3 "$SKILL_ROOT/scripts/audit_batches.py" assign "$REPORT_DIR/inventory.json" --batch-size 20 --out "$REPORT_DIR/batches"
python3 "$SKILL_ROOT/scripts/audit_batches.py" import "$REPORT_DIR/batches/<batch file>" <rows.json> --accepted "$REPORT_DIR/scores.json"
```

Each score row carries its `batch_id` and `source_digest`. An import that has missing, extra, duplicate, malformed, or foreign rows, or a batch file stripped of its selection rule, counts, or non-probability note, exits 1 and leaves the accepted file unchanged. A changed inventory needs a new assignment.

## Report sections and export

`assemble_report.py` writes the `audit` object for local browsing. The renderer exits 1 when the scorecard and the artifact disagree, so a hand-edited score is caught.
`report.html` keeps paths and session ids for local use. To share results, run `python3 "$SKILL_ROOT/scripts/public_export.py" "$REPORT_DIR/report.json" --out <path>`; it writes aggregates only and exits 1 if any private value reaches the export, or if `grade` or the `evaluation` fields hold text outside their fixed vocabulary.
