# code-review catch-rate harness

Measures how often the repository's code reviewer flags a real bug that this
repository's own history shows it shipped and later fixed. Issue #7149 asks for
a regression number, so a model swap, a prompt edit, or a harness change gets a
measurement instead of an opinion. This directory holds the corpus, the method,
and the results. The harness only produces the number. The repository owner
judges whether a number is enough.

## Question

If the `code-reviewer` had reviewed the change that introduced each bug, how
often would one of its top five findings have named that bug?

## Pinned decisions

These were fixed before any model ran, so no result can move them.

| Decision | Pin |
|---|---|
| What the reviewer sees | The introducing diff and its commit subject. Nothing else. No fixing commit, no later history, no repository checkout, no tools. |
| What counts as a match | A finding names the same file and the same defect class as the corpus entry. |
| How many findings count | The first five, in the order the reviewer wrote them. |
| Who scores | A deterministic rule in code. No model judges another model. |
| Interval | 95 percent Wilson score interval, the function the ADR harness uses. |

## Results

Baseline, run 2026-11-10: model `claude-sonnet-5` (the harness default) through
the `claude-cli` provider, one trial per entry, 32 calls, 583,677 output tokens,
25 minutes wall clock with 4 workers. Cost: a subscription CLI, so no metered
spend and no dollar figure. No call errored. Saved files: `results/2026-11-10-claude-sonnet-5.json` (every row and the
aggregate), `results/2026-11-10-claude-sonnet-5.md` (the report), and
`runs/2026-11-10-claude-sonnet-5-rows.jsonl` (the 32 full responses, so any hit or
miss can be audited and `--rescore` reproduces the numbers with no model call).

| Measure | Result (n = 32, 95 percent Wilson interval) |
|---|---|
| Caught in top 5 (same file and class) | 3/32 (9%, CI 3% to 24%) |
| Same file in top 5 (class ignored) | 10/32 (31%, CI 18% to 49%) |

Which model: `claude-sonnet-5` is `DEFAULT_MODEL` in `scripts/eval/_anthropic_api.py`,
the harness default. The `code-reviewer` agent pins no model (ADR-119) and
inherits each harness's default, which can differ from it. Issue #7149 asks for
the "current default model"; this run measures the eval default, not a measured
day-to-day reviewer model. Pass `--model` to measure another.

`corpus.json` was reformatted after this run (whitespace only, to fit the 500-line
taste limit). The `corpus_sha256` in the results file is the hash of the committed
file, and `--rescore` on the saved rows reproduces the table above against it.

Hits: CR08, CR14, CR22. Seven more reviews named the right file under another
class (CR01, CR04, CR09, CR10, CR12, CR13, CR25). Sixteen reviews returned
`NO FINDINGS`.

Per class: edge-case 2/8, logic-error 1/9, and 0 of 15 across test-defect (5),
error-handling (4), concurrency (2), security (2), config-wiring (1) and
resource-handling (1). Every interval at this size is wide, so read the split as
direction, not rate.

### Reading the numbers

- **This is a floor, not a verdict on the reviewer.** The replay gives the model
  the diff and nothing else. The CRBugBench study reports 71.9 percent for its
  best agent, which explores a checkout; that figure measures a different task
  (tools, project context, a different bug set) and is not comparable to 9 percent.
  The point of this number is to move when a model, prompt or harness changes.
- **Half the reviews said there was nothing to report.** The contract tells the
  reviewer to report only at confidence 80 or above and, with no repository access,
  to treat its own context as partial; CR05's answer says so. A different prompt
  could trade precision for recall; this run does not test that.
- **The parse is faithful.** All 16 empty rows end in an explicit `NO FINDINGS`.
  A reader checked the matched text of all three hits against the corpus defect:
  CR08 names the whole-string pytest-summary search, CR14 the credentialed HTTPS
  remote, CR22 the missing `issuecomment` handling on a pull request URL. All
  three describe the entry's defect.
- **The class rule costs 7 reviews.** The gap between 10 same-file reviews and 3
  catches is class labelling. For example the corpus files CR01 as `logic-error`
  and the reviewer tagged its findings `error-handling`. Whether each of the seven
  tags is a fair reading was not audited. The strict number is the headline because
  the issue pins "same file and defect class"; the same-file number bounds how much
  a looser class rule would add.

## Corpus

`corpus.json` holds 32 bug pairs from this repository's history. Each entry names:

- `introducer`: the commit that introduced the bug. The reviewer sees its diff.
- `fix`: the commit that repaired it. The reviewer never sees it.
- `introducer_ref` and `link_evidence`: the PR or commit the fix cites, and the
  line of the fix message that cites it. This is the explicit link.
- `defect`: one or two sentences about what was wrong in the introduced code.
- `defect_files`: the paths in the introducing diff that hold the defect. A
  mirrored copy of a file in the same diff is listed too.
- `defect_class`: one of the nine classes in Scoring.
- `confidence`: `high` when the fix message states the causal link, `medium` when
  the link is inferred from the fix diff.
- `fix_subject` and `fix_date`: for audit only. The leak check proves neither
  reaches the reviewer.

The corpus stores commit ids, not text. The runner reads the diff with `git show`.
Composition at 2026-11-10: logic-error 9, edge-case 8, test-defect 5,
error-handling 4, security 2, concurrency 2, resource-handling 1, config-wiring 1.
Confidence: 13 high, 19 medium. Fix dates run from 2026-06 to 2026-11.

### Selection rule

The rule is stated in `corpus.json` under `selection.rule`, so no entry is chosen
by feel. A bug enters the corpus only with an explicit introducer link:

1. Universe: the 4,014 commits reachable from `b959011e3` (2026-11-10), of which
   1,628 have type `fix`.
2. The fix message cites an earlier PR (resolved through the `(#N)` suffix of its
   squash commit) or an earlier commit SHA.
3. `git blame` at the fix's parent attributes at least one line the fix removes
   or changes in a `.py` file to the cited commit. This is the mechanical check
   that the cited change really introduced the repaired lines. 160 commits pass
   (51 from a first pass keyed on words such as "regression" and "introduced",
   109 from the remaining `fix` commits).
4. The cited commit's diff over reviewable files is at most 110,000 characters
   (39 commits fall out here). Reviewable files exclude `.md`, `.mdx`, `.txt`,
   `.json`, `.jsonl`, `.lock` and anything under `.project-toolkit/`, `.agents/`,
   `.serena/` and `docs/`.
5. Vetting: 121 candidates reach this step; 32 are accepted and 89 rejected. The
   criteria are in `selection.vetting.criteria`. In short: the fix corrects a
   behavioral defect (not wording, a refactor, a feature or a baseline update);
   the defect sits in lines the introducer wrote; a reader of the introducing
   diff alone could in principle see it; it fits in one or two sentences.

`selection.candidates_rejected` lists every rejected candidate with a reason.
Accepted candidates are the entries. Rejected-for-size and unlinked commits are
counted in `selection.funnel`, not listed one by one.

Vetting was done by Sonnet subagents applying the criteria, then one reader
(Claude) read all 32 accepted descriptions and checked four against the fix diff.
No repository maintainer has reviewed the entries. Issue #7149 asks for
"human-checked" descriptions, so that bar is not yet met. The descriptions are
the thing to review: `defect`, `defect_files` and `defect_class` per entry.

`--validate-corpus` re-checks what a machine can: every commit is readable, every
`defect_files` path appears in the reviewed diff, every diff is under the cap, and
no prompt carries fix content.

## Scoring

The reviewer is asked to write each finding on one line:

```text
FINDING: <path>:<line> | <class> | <one sentence naming the defect>
```

`<class>` is one of `logic-error`, `edge-case`, `error-handling`, `security`,
`concurrency`, `api-contract`, `test-defect`, `config-wiring`, or
`resource-handling`. A reviewer with no finding writes `NO FINDINGS`.

Per review, over the first five `FINDING:` lines:

- **Caught**: one finding names a file in the entry's `defect_files` and the
  entry's `defect_class`. A path matches when it is equal, or when one path is a
  suffix of the other at a `/` boundary, so a reviewer that drops a directory
  prefix still matches and a mirrored copy of the file also matches.
- **Near miss**: a finding names the right file with another class. It is not a
  catch. The report shows it so the owner can see how much of a miss is class
  labelling and how much is the reviewer looking elsewhere.
- **Miss**: anything else, including an answer with no findings.

The headline number is **caught**. The report also gives the same-file rate with
the class ignored, the rate per defect class, and a per-entry table.

An errored call counts toward `errors`, never toward `n`, so a failing provider
cannot lower a rate by looking like a miss. `--rescore --checkpoint rows.jsonl`
re-scores stored responses with the current rules and makes no model call.

## Leak guarantee

The reviewer must not see the fix. Three mechanisms enforce it, and the tests
cover each:

1. `build_review_input` takes the introducing commit alone. Its signature has no
   fixing-commit parameter, and a test records every `git` call it makes and
   asserts none names the fix.
2. `--validate-corpus` builds every prompt, then checks that none contains the
   fixing commit's SHA (full or 12 characters), its subject, its added lines of
   40 characters or more that the introducing patch does not also contain, or the
   corpus defect description. Any hit exits 2.
3. A runner test sends four prompts through a stub reviewer and asserts that
   none carries text the fix added.

## Run

```bash
uv run python scripts/eval/eval_code_review_catch_rate.py --validate-corpus
EVAL_PROVIDER=claude-cli uv run python scripts/eval/eval_code_review_catch_rate.py \
    --workers 4 --checkpoint rows.jsonl --output results.json --report report.md
```

`--dry-run` prints the call count. `--checkpoint` makes a run resumable.
`--report-from results.json` re-renders a saved report. The corpus stores commit
ids, not text, so the commits must be present locally (`git fetch --unshallow`
on a shallow clone).

## Follow-up phases

Both depend on this corpus and this baseline. Neither is started.

- **Phase 2, issue #7151:** A/B test an exploration-nudged variant of the
  reasoning protocol in `technical-review.md` against the current contract, same
  model, same corpus. At n = 32 the interval on one arm is 20 to 34 points wide, so
  a 5.8-point difference cannot be told from noise. Phase 2 needs a larger corpus,
  several trials per entry, or a paired design before it can run.
- **Phase 3, issue #7152:** dispatch review models by pull request traits (size
  band, security paths, public API, test-only). 32 entries split into 4 bands is
  about 8 per cell, too few to separate models. Phase 3 needs a larger corpus too.

## Limits

- **The corpus is small.** 32 entries gives a 95 percent interval about 30 points
  wide at a 50 percent rate. A change of a few points between two runs is noise.
  A per-class or per-band split leaves a handful of entries per cell.
- **It measures bugs already found.** Every entry was found and fixed by someone
  after the introducing change landed. It says nothing about bugs nobody has
  found.
- **Selection is biased toward visible links.** An entry needs a fix message that
  cites its introducer and a blame trail inside `.py` files. Bugs fixed with a
  silent commit, or in YAML, shell or Markdown only, are absent. The 110,000
  character cap removes large PRs, where review is hardest.
- **Several entries come from review-round follow-ups.** Many fix commits are
  titled "follow-up to #N". A reviewer that sees the introducing PR before merge
  is closer to the author's own review round than to a cold reader.
- **The replay is single-turn and tool-free.** The reviewer sees the diff and the
  commit subject, with no checkout, no callers and no tests. The real
  `code-reviewer` agent has read and search tools. The Microsoft Research study
  reports that project context decides the answer, so this number likely
  understates what the agent finds with tools. This design cannot say by how much.
- **The output shape is constrained.** The harness asks for `FINDING:` lines in
  place of the contract's finding shape (location, disposition, evidence, impact,
  remediation, confidence). The contract's 80 percent confidence threshold still
  applies in the prompt, so a reviewer may withhold a real but uncertain finding.
- **The class tag is the reviewer's own.** A correct finding tagged with another
  class counts as a near miss, not a catch. The near-miss and same-file columns
  show the size of that effect.
- **Descriptions are model-drafted.** See Corpus. CR09, CR12, CR21, CR23 and CR32
  name one of several defects their fix repaired; a finding on another defect in
  the same file and class still counts.
- **One model, one trial per cell** unless the run says otherwise. The report lists
  the model and the trial count. Repeat trials of one entry are not independent
  samples of the corpus.
- **Subscription transport reports no dollar cost.** The `claude-cli` provider
  bills a subscription, so results record calls and output tokens, not dollars.
