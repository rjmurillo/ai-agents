# Comment Actionability Eval

This eval decides whether a model fallback beats the review comment heuristic.
The spec is `.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md`.
The plan is `.project-toolkit/plans/active/harness-agnostic-llm-fallback.md`.

## Files here

| File | What it is |
|---|---|
| `band-measurement.json` | Share of comments in the 0.4 to 0.6 band. Kill criterion 1. |
| `RUBRIC.md` | How to label a comment actionable or not. |
| `prompt-v1.md` | System prompt for arm C. Freeze it before held-out scoring. |

Corpus, sheet, and prediction files hold comment text. Keep them in
`.project-toolkit/scratch/`, which git ignores. Do not commit them.

## Run it

Run every step from the repository root. Steps 1 and 3 need a `gh` login.
Step 7 needs `ANTHROPIC_API_KEY`, or a `--provider` that `call_api` accepts.

1. Measure the band and save the raw PR nodes.

   ```bash
   uv run python scripts/eval/measure_actionability_band.py --days-back 90 \
       --save-prs .project-toolkit/scratch/band-prs.json \
       --output evals/comment-actionability/band-measurement.json
   ```

2. Draw the corpus: 100 band rows, 100 outside rows, 40 band rows marked dev.

   ```bash
   uv run python scripts/eval/actionability_corpus.py sample \
       --prs .project-toolkit/scratch/band-prs.json \
       --output .project-toolkit/scratch/corpus.jsonl
   ```

3. Fetch each row's diff hunk. Rerun the same command to resume after a failure.

   ```bash
   uv run python scripts/eval/actionability_corpus.py fetch-hunks \
       --corpus .project-toolkit/scratch/corpus.jsonl \
       --output .project-toolkit/scratch/corpus.jsonl
   ```

4. Write the blinded sheet. It holds only id, path, diff hunk, body, and label.

   ```bash
   uv run python scripts/eval/actionability_corpus.py sheet \
       --corpus .project-toolkit/scratch/corpus.jsonl \
       --output .project-toolkit/scratch/sheet.jsonl
   ```

5. Label the sheet per `RUBRIC.md`. Set `label` to `actionable`,
   `not_actionable`, or `unsure`. A council of 3 non-Anthropic models labels
   it, and the majority vote is the label. Stop if all three agree on fewer
   than 70 percent of items. The owner spot-checks 20 seeded items. The
   council tooling is plan task M1-T11 and is not built yet.

6. Merge the labels back into the corpus.

   ```bash
   uv run python scripts/eval/actionability_corpus.py merge-labels \
       --corpus .project-toolkit/scratch/corpus.jsonl \
       --sheet .project-toolkit/scratch/sheet.jsonl \
       --output .project-toolkit/scratch/labeled.jsonl
   ```

7. Tune the prompt on the dev split. Edit `prompt-v1.md` between runs, and use
   a fresh `--output` each time, since every record carries the prompt hash.

   ```bash
   uv run python scripts/eval/actionability_arms.py predict \
       --corpus .project-toolkit/scratch/labeled.jsonl \
       --split dev --model MODEL \
       --output .project-toolkit/scratch/predictions-dev.jsonl
   ```

   Then commit `prompt-v1.md` to freeze it, and predict the held-out split. A
   rerun with the same `--output` skips rows already done.

   ```bash
   uv run python scripts/eval/actionability_arms.py predict \
       --corpus .project-toolkit/scratch/labeled.jsonl \
       --split heldout --model MODEL \
       --output .project-toolkit/scratch/predictions.jsonl
   ```

8. Score the three arms. The verdict is `pass` when the gap is at least 0.10
   and the CI lower bound is above 0, `fail` only when the CI upper bound is
   under 0.10, and `inconclusive` otherwise. On a look-1 `inconclusive`, label
   100 more band items once and rerun with `--look 2 --look1-report
   .project-toolkit/scratch/score.json`. Look 2 exits 2 unless that report is an
   inconclusive look 1 and the corpus holds at least 100 more heldout band rows.

   ```bash
   uv run python scripts/eval/actionability_arms.py score \
       --corpus .project-toolkit/scratch/labeled.jsonl \
       --predictions .project-toolkit/scratch/predictions.jsonl \
       --output .project-toolkit/scratch/score.json
   ```

## Secret scan

`sample`, `fetch-hunks`, and `predict` scan comment text, replies, file paths,
and hunks.

- A token shape or a credential assignment blocks the step. Nothing is written,
  and no model call is made.
- A 40 character hex run is a git commit SHA. It is reported, not blocked.
- A 64 character hex run blocks. It may be a sha256 digest or a 256-bit key.
- A 32 character hex run after `pr-review-job-` or `Syntactic id:` is a
  public reviewer bot id. It is counted, not blocked.
- Any other hex run blocks. After you read the row, pass its id with
  `--allow-hex-rows ID[,ID...]`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done |
| 1 | The secret scan blocked a row |
| 2 | Bad input or configuration, such as a missing key or unlabeled rows |
| 3 | GitHub or the model failed |
| 4 | The model refused the key (401 or 403) |
