# Skill-doctor audit reproduction

Reproduce a full skill-doctor audit report from a clean checkout. No real conversations and no network are needed.
The outcome: four files that match the committed copies in `expected/`.
This recipe serves the skill lifecycle training in issue #7208, and `test_audit_reproduction.py` checks each command on every run.

## Inputs

All inputs are synthetic. Every private value carries a `CANARY-` prefix, so a leak into the public summary is easy to find.

| File | What it holds |
| --- | --- |
| `scores.json` | Six scored sessions across two harnesses and two strata. One code-quality `block`, three `insufficient_evidence`, and one session cut off by a provider limit. |
| `draft.json` | The report without numbers: findings, one unevaluated suggestion, stats, and sampling counts. |
| `audit_manifest.json` | A catalog with three definitions: two contents for `alpha` and one alias. |

## Run it

From the repository root, after `uv sync`:

```bash
FIXTURES=tests/skills/skill-doctor/fixtures/audit/reproduction
SCRIPTS=src/claude/skills/skill-doctor/scripts
OUT="$(mktemp -d)"
python3 "$SCRIPTS/audit_scores.py" "$FIXTURES/scores.json" --out "$OUT/score_artifact.json"
python3 "$SCRIPTS/assemble_report.py" "$FIXTURES/draft.json" --scores "$FIXTURES/scores.json" --artifact "$OUT/score_artifact.json" --manifest "$FIXTURES/audit_manifest.json" --out "$OUT/report.json"
python3 "$SCRIPTS/render_report.py" "$OUT/report.json"
python3 "$SCRIPTS/public_export.py" "$OUT/report.json" --out "$OUT/public.json"
```

Each command exits 0. The second prints `overall: 0.8579 from 6 sessions`.

## Check the result

```bash
for f in score_artifact.json report.json public.json; do
  python3 -m json.tool --sort-keys --compact "$OUT/$f" | diff - "$FIXTURES/expected/$f"
done
```

The loop prints nothing: all three match. The copies in `expected/` are stored in that sorted, compact form. `expected/report.html` is the rendered page with two parts normalized: the render timestamp and the embedded diff viewer bundle, which `test_vendored_bundle.py` covers on its own.

What to look for in the outputs:

- `score_artifact.json`: code quality has a denominator of 3 and 3 inapplicable results. Insufficient evidence is not a failure.
- `score_artifact.json`: `failed_conversations` leaves out the session cut off by the provider, because its only low score judges the cut-off ending.
- `report.json`: `scores` and each `sampling.per_harness.<harness>.overall` come from the artifact, not from a hand copy.
- `public.json`: aggregates only. It has no `CANARY-` value, no path, and no session id.

## Change the outputs on purpose

When a script change is meant to change these outputs, refresh the copies and review the diff before you commit:

```bash
SKILL_DOCTOR_UPDATE_GOLDEN=1 uv run pytest tests/skills/skill-doctor/test_audit_reproduction.py
```
