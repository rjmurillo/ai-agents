# Third-party review gap

What did this repository's author agents ship that a third-party review bot
then caught, and the author agreed and fixed? This directory holds the mined
findings, two eval corpora built from them, and the measured effect of two
changes meant to catch those defects before a pull request opens. One change
closed its gap and ships (Eval 1). The other showed no gain and does not ship
(Eval 2).

## Question

On the 1000 newest pull requests, which defects did Devin, Cursor Bugbot,
CodeRabbit, the Copilot reviewer, and Semgrep find after the author's own
pipeline passed? Which of them can the repository catch itself, and does a
proposed change catch more of them?

## Data

Read on 2026-11-15 from `rjmurillo/ai-agents`: pull requests #6110 to #7380,
newest 1000 by creation (972 merged, 20 closed, 8 open; 829 opened by the agent
account). Every review thread, review, and top-level comment was paged to the
end (`scripts/eval/mine_third_party_review_findings.py`, 77 GraphQL requests,
477 points). The raw dump is not committed; it holds third-party comment text.

| Bot | PRs it reviewed | Threads it opened | Admitted findings | Admitted per reviewed PR |
|---|---|---|---|---|
| Devin | 356 | 570 | 365 | 1.03 |
| Cursor Bugbot | 165 | 387 | 212 | 1.28 |
| CodeRabbit | 79 | 272 | 124 | 1.57 |
| Copilot reviewer | 15 | 78 | 40 | 2.67 |
| Semgrep | 20 | 69 | 7 | 0.35 |
| CodeQL | 5 | 14 | 0 | 0 |

Coverage was partial. Bugbot posted 1051 "usage limit reached" notices and the
Codex connector 999, so most pull requests got no review from them. Every count
below is a floor on what the bots would have found.

### Admission

A bot thread becomes a finding in `findings.jsonl` (one finding per line)
only when the author's reply cites a fix commit, that commit resolves locally,
it touches the thread's path, and it descends from the commit the bot reviewed.
`scripts/eval/build_third_party_gap_corpus.py` applies these steps to a saved
dump and rebuilds every corpus file here; `--check` confirms the committed
files match a rebuild, and `--stats` prints the other counts this page cites.

| Step | Count |
|---|---|
| Bot-opened threads | 1390 |
| Author accepted (reply or bot "addressed" marker) | 963 |
| Reply cites a fix commit | 817 |
| Fix commit does not resolve | 1 |
| Fix commit does not touch the thread's path | 68 |
| **Admitted** | **748** |

`split` is `heldout` for PR #7066 and later (264 findings), `derive` before it
(484). Proposals were written from the derive split; held-out numbers are the
test.

`defect_class`, `theme`, `context_needed`, `mechanical`, and `summary` were
drafted by a model in one pass and are not hand-audited. The labels are in
`labels.jsonl`, and the instructions the model followed are in
`label-brief.md`. A read of 28 held-out
rows disagreed with about 5 `context_needed` labels, roughly 18 percent, mostly
regex defects labeled `external-knowledge` that a diff reader could see.

## What the bots caught

| Theme | Findings | Share |
|---|---|---|
| doc-code-drift | 131 | 17.5% |
| parsing-too-narrow-or-broad | 75 | 10.0% |
| platform-portability | 71 | 9.5% |
| state-or-ordering | 66 | 8.8% |
| unhandled-input | 59 | 7.9% |
| contract-mismatch | 58 | 7.8% |
| other | 58 | 7.8% |
| vacuous-or-weak-test | 54 | 7.2% |
| sibling-path-missed | 53 | 7.1% |
| repo-convention | 50 | 6.7% |
| fail-open | 45 | 6.0% |
| security | 28 | 3.7% |

By context: 390 need a file outside the diff, 270 are visible in the diff
alone, 88 need knowledge of an outside system. 100 of 748 are mechanical: a
static check could flag them.

Three facts change what to fix:

1. **Cursor's strongest rules live outside the repository.** 166 Bugbot threads
   cite a "learned rule" stored in Cursor's service. The author agents never
   see them. The top three (subprocess text mode without an encoding,
   `read_text`/`write_text` without an encoding, test symlinks with no Windows
   skip) account for 86 threads the author fixed or resolved.
2. **False prose is new prose.** 197 of the 200 `doc-accuracy` findings sit on
   lines the pull request itself added. The review pipeline does not check a
   new sentence's claim against the code it describes.
3. **Running `/review` barely moved the count.** Revisions whose commits carry
   a `/review` marker drew 1.91 admitted findings each; revisions without one
   drew 2.01. The marker is required only for workflow and hook paths, so this
   compares populations, not a controlled change.

## Eval 1: deterministic checks

`io-portability-corpus.json`: 86 Bugbot learned-rule findings (33 derive, 53
held out). `scripts/eval/eval_io_portability_gap.py` reads each file at the
commit Bugbot reviewed and asks, with no model call, whether a check flags a
line within 3 of Bugbot's line.

| Arm | All | Derive | Held out |
|---|---|---|---|
| Baseline: `check_subprocess_encoding.py` plus `ruff` with this repository's config | 0/86 (CI 0% to 4%) | 0/33 | 0/53 |
| Treatment: `scripts/validation/check_io_portability.py`, whole file | 78/86 (CI 83% to 95%) | 33/33 | 45/53 |
| Treatment as shipped: only lines the pull request added | 78/86 (CI 83% to 95%) | 33/33 | 45/53 |

Per rule: subprocess encoding 32/34, file encoding 25/25, unguarded symlink
21/27. Files: `results/io-portability-summary.json`, per row
`results/io-portability-rows.jsonl`.

The baseline is 0 for two reasons: `check_subprocess_encoding.py` scans only
`scripts/` and flags only `encoding="utf-8"` without `errors`, and `ruff`'s
`PLW1514` is preview-only and not selected.

Honest caveats:

- The first treatment run scored 53/86. Bugbot anchors some findings on a
  call's closing parenthesis, so the match was widened to the whole call span
  after reading misses that included held-out rows.
- Negative control: in 7 rows the file at the pull request's final head has no
  fewer violations of the rule than at the reviewed commit. Six are rows the
  checker missed (0 before, 0 after). The seventh, T0396, is a finding the
  author never fixed.
- Precision, in the mode that ships (added lines only): over the 170 held-out
  merged pull requests whose head commit is present locally (of 215), the
  check flags 49 lines in 15 pull requests (9%). Twenty sampled flags on files
  Bugbot never threaded were all real. `--stats` reproduces the count.
- The whole tree holds 2794 violations, so the check runs on added lines only
  and skips generated mirror trees and `fixtures/` directories.

The check now runs in `pre_pr.py` as the blocking gate `IO Portability (added
lines)`.

## Eval 2: model replay of the reviewer

`replay-corpus.json`: 237 reviewed revisions (186 derive, 51 held out), every
admitted finding whose path is in the pull request diff (merge base to the
reviewed commit) and whose diff is at most 110000 characters. Three revisions
were dropped because their fix edited the reviewer prompt itself, which the
leak check caught.

`scripts/eval/eval_third_party_gap_replay.py` shows the `code-reviewer` agent
template plus `technical-review.md`, read at a git ref, the pull request diff
with new-file line numbers, and nothing else. A defect counts as caught when a
top-10 finding names its file and a line within 10 of the bot's line.
No model judges another model.

Treatment: the "Defect hunt" section in
`src/claude/skills/review/resources/technical-review.md` (six checks: matchers,
failure paths, prose claims, siblings, tests, inputs), written from the derive
split only. Baseline: the same files at `c98e82b21`, this branch's fork point.
At that commit `templates/agents/code-reviewer.shared.md` differs from `main`
by a two-line rewrite of where the agent looks for the contract file. The
replay inlines the contract, so that text does not change what it measures.

Decision rule, written on 2026-11-15 after an interim look at 57 of 102 jobs
per arm and before the final numbers: keep the treatment only when, on the
held-out split, the treatment arm catches more defects than the baseline arm
and the exact two-sided McNemar test on the defects one arm caught and the
other missed gives p below 0.05. Otherwise the contract edit leaves this change
and stays a recorded null result. Same-file hits and empty reviews are
reported but do not decide. `--compare` computes the test.

### Result

Held-out split, 51 revisions, 81 defects, 2 trials per arm (162 defect-trials
per arm, 204 calls), run 2026-11-15. Model `claude-sonnet-5` through an
OpenAI-compatible proxy with thinking on. No call errored and no answer
reached the output ceiling.

| Arm | Caught | Same file | Empty reviews | Output tokens |
|---|---|---|---|---|
| Baseline (`c98e82b21`) | 18/162 (11.1%, CI 7.1% to 16.9%) | 46 | 40 of 102 | 2,403,036 |
| Treatment (defect hunt) | 21/162 (13.0%, CI 8.6% to 19.0%) | 61 | 30 of 102 | 2,657,228 |

Paired by defect-trial: 9 both, 9 baseline only, 12 treatment only, 132
neither. Exact McNemar p = 0.66. By context: diff-local 3 vs 4 (p = 1.0),
repo-context 4 vs 7 (p = 0.55), external-knowledge 2 vs 1 (p = 1.0).

**Verdict: no measurable gain. The treatment fails the decision rule and is
not part of this change.** `technical-review.md` is unchanged from `main`.

What the run does show:

- **Noise is as large as the effect.** The baseline's two trials of the same
  prompt disagree on 14 of 81 defects (11 caught only in trial 0, 3 only in
  trial 1). The arms disagree on 21 of 162. A prompt change needs more trials
  or a larger held-out set before a few points can be read as signal.
- **Prompting moved where the reviewer looks, not what it proves.** Same-file
  hits rose from 46 to 61 and empty reviews fell from 40 to 30, but the line
  match did not follow.
- **The replayed reviewer catches no platform-portability defect.** 0 of 44 in
  both arms. The deterministic check in Eval 1 catches 78 of 86 of that kind.
  That class belongs to a static gate, not a prompt.

Files: `results/replay-heldout-baseline.json`,
`results/replay-heldout-treatment.json`, `results/replay-heldout-compare.json`,
and every answer in `runs/replay-heldout-*-rows.jsonl`. Each rows file holds
105 lines for 102 jobs: a process restart wrote 3 jobs twice, and the loader
keeps the first finished row per job. `--rescore` and `--compare` rebuild the
results from those files with no model call. A rebuilt result says
`rebuilt_from_checkpoint` and reads prompt ref, model, and provider from the
rows. These rows predate that stamp and say `not recorded`; the run parameters
above are the ones that applied. New runs write them on every row.

## Run

```bash
uv run python scripts/eval/mine_third_party_review_findings.py --limit 1000 --output dump.json
uv run python scripts/eval/build_third_party_gap_corpus.py --dump dump.json --check --stats
uv run python scripts/eval/eval_io_portability_gap.py --output summary.json --rows rows.jsonl
uv run python scripts/eval/eval_third_party_gap_replay.py --split all --validate-corpus
EVAL_PROVIDER=openai OPENAI_BASE_URL=<compatible endpoint> EVAL_HTTP_TIMEOUT_SECONDS=1800 \
  uv run --extra eval python scripts/eval/eval_third_party_gap_replay.py \
  --split heldout --trials 2 --model claude-sonnet-5 --prompt-ref <ref> \
  --checkpoint rows.jsonl --output result.json
uv run python scripts/eval/eval_third_party_gap_replay.py --split heldout \
  --checkpoint treatment-rows.jsonl --compare baseline-rows.jsonl
```

The replay never caps an answer to save tokens; each row records its output
tokens and finish reason. An HTTP 429 is retried with backoff because the
provider rejects it before generating anything. A timeout is not retried.

## Limits

- **Floors, not rates.** Bots were rate limited for most of the window, and
  a finding the author rejected or never answered is not in the corpus.
- **Model-drafted labels.** See Admission.
- **The replay has no tools.** 52 percent of findings need a file outside the
  diff, and a tool-free reviewer cannot see it. The real `code-reviewer` reads
  and searches the repository.
- **One model.** `claude-sonnet-5` through an OpenAI-compatible proxy with
  thinking on. The harness default reviewer model may differ.
