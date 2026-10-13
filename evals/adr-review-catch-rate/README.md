# adr-review catch-rate harness

Measures how often each adr-review role flags a defect that the ADR-100/101
debate later fixed. ADR-101 abandons its Phase 2 unless a published per-role
catch rate justifies it (issues #5247 and #5248). This directory holds the
corpus, the method, and the results. The repository owner judges whether a
number is enough. The harness only produces the number.

## Question

If the six adr-review roles had reviewed the ADR text as it stood before each
fix, how many of them would have flagged the defect?

## Results

Run on 2026-10-13: model `claude-sonnet-5` through the `claude-cli` provider,
one trial per cell, 270 calls (20 entries x 6 roles x unassisted and control,
plus 5 entries x 6 roles assisted). No saved row carries an error. Saved results:
`results/2026-10-13-claude-sonnet-5.json` (every row, the matched finding
text, and the SHA-256 of each full response) and `results/2026-10-13-claude-sonnet-5.md`.

Per-role rate on the unassisted arm (n = 20 defects per role, 95 percent Wilson
interval):

| Role | Mentioned | Flagged | Blocked |
|---|---|---|---|
| architect | 7/20 (35%, CI 18% to 57%) | 1/20 (5%, CI 1% to 24%) | 0/20 (0%, CI 0% to 16%) |
| critic | 8/20 (40%, CI 22% to 61%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) |
| independent-thinker | 6/20 (30%, CI 15% to 52%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) |
| security | 9/20 (45%, CI 26% to 66%) | 2/20 (10%, CI 3% to 30%) | 0/20 (0%, CI 0% to 16%) |
| analyst | 6/20 (30%, CI 15% to 52%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) |
| high-level-advisor | 4/20 (20%, CI 8% to 42%) | 0/20 (0%, CI 0% to 16%) | 0/20 (0%, CI 0% to 16%) |
| any role | 16/20 (80%, CI 58% to 92%) | 2/20 (10%, CI 3% to 30%) | 0/20 (0%, CI 0% to 16%) |

Assisted arm (n = 5 defects per role, the five that carry evidence excerpts):
architect 1/5 flagged and 1/5 blocked, security 1/5 flagged, every other role
0/5. Any role: 2/5 flagged, 1/5 blocked. The per-role intervals at n = 5 span
at least 40 points, so the assisted figures show direction, not a rate.

### Reading the numbers

- Some role looked at the area of 16 of 20 defects and flagged 2. The panel
  read the right paragraphs and mostly did not see what was wrong with them.
- No role blocked on any defect in the unassisted arm, so on this corpus a
  single no-access pass never stops a review for these defects.
- The deterministic rule overcounts. A single reader audited all five
  non-control hits against the stored text. Three stand: D09 by security
  (unassisted), D01 by architect (assisted, blocked), and D07 by security
  (assisted). Two do not: D08 by architect is a question about a runbook, and
  D08 by security describes the base-update race the ADR already covers, not the
  fetch-by-pull-request-number race. Audited unassisted catch: 1 of 20 defects
  (security on D09). Audited assisted catch: 2 of 5 (D01, D07). This audit is
  one reader, not independent, so the `matched` text of every hit is in the
  results file for the owner to check.
- The control arm is not a false-flag floor. The post-fix text states the
  repaired claim, so the four control hits (D06, D08, D09 by security; D18 by
  high-level-advisor) are reviewers quoting the correction. Read the control
  column as how often the rules fire on text that discusses the defect, not as
  noise on clean text.
- Other real defects exist in the same pre-fix texts. For example, the
  independent-thinker flagged the skipped-equals-success contradiction inside
  ADR-101 on the D07 text, a defect outside this corpus. The corpus therefore
  understates what a pass finds in total. It does not overstate what the pass
  finds of the 20 seeded defects.

Per-defect detail (unassisted roles that mention the area out of 6, and the
roles whose finding matched):

| Entry | Kind | Mention it | Flag it (unassisted) | Flag it (assisted) |
|---|---|---|---|---|
| D01 | internal-contradiction | 0 | none | architect |
| D02 | logic-gap | 3 | none | not run |
| D03 | internal-contradiction | 0 | none | not run |
| D04 | factual-overclaim | 1 | none | not run |
| D05 | factual-overclaim | 3 | none | not run |
| D06 | unsupported-causality | 6 | none | none |
| D07 | logic-gap | 3 | none | security |
| D08 | security-hole | 1 | architect, security (both rejected on audit) | not run |
| D09 | security-hole | 3 | security | not run |
| D10 | internal-contradiction | 4 | none | not run |
| D11 | security-hole | 1 | none | not run |
| D12 | security-hole | 0 | none | not run |
| D13 | security-hole | 0 | none | not run |
| D14 | arithmetic | 1 | none | not run |
| D15 | logic-gap | 2 | none | not run |
| D16 | security-hole | 2 | none | not run |
| D17 | internal-contradiction | 6 | none | not run |
| D18 | factual-overclaim | 1 | none | none |
| D19 | omission | 1 | none | not run |
| D20 | omission | 2 | none | none |

What this does not say: whether the number justifies ADR-101 Phase 2. Issue
#5247 leaves that judgment to the repository owner.

Provenance of the rows: 78 rows come from a first launch whose stored
responses were whole, and 192 from a second launch with the same command. The
first launch capped stored text, which hid the tail of 72 long responses; the
harness now keeps whole responses and retries any truncated row. All 270 rows
were scored together with `--rescore` under the final rules. Full responses are
not committed (about 3 MB); the SHA-256 in each row identifies one.

## Corpus

`corpus.json` holds 20 seeded defects from the ADR-100/101 debate on PR #5181.
Each entry names:

- `base_commit`: the commit whose ADR text is replayed (the parent of the fix).
- `fix_commit`: the commit that repaired the defect.
- `anchor`: a verbatim span of the pre-fix text that carries the defect. The
  loader refuses an entry whose anchor is absent from the pre-fix text.
- `defect`: one sentence stating what was wrong.
- `kind`: factual-overclaim, internal-contradiction, logic-gap, security-hole,
  arithmetic, unsupported-causality, or omission.
- `evidence`: bounded repository excerpts (at most 60 lines) that a verifying
  reviewer would read. Empty when the defect is checkable from the text alone.
- `match`: the deterministic detection rule (see Scoring).

The corpus stores commit ids, not text. The runner reads the text with
`git show`. The commits live on the head of PR #5181, which is squash-merged,
so fetch them once:

```bash
git fetch origin refs/pull/5181/head:refs/tmp/pr5181
```

### Selection rule

The rule is stated in `corpus.json` under `selection.rule` so no entry is
chosen by feel. In short:

1. Universe: every commit that changes ADR-100 or ADR-101 on the head of
   PR #5181, plus post-merge fix commits that cite the same debate. That is 29
   commits.
2. Include a commit when its subject type is `fix`. Fourteen are included.
3. From an included commit, seed each defect that is a wrong claim or missing
   step in a span of the pre-fix text, is checkable from the text or a bounded
   excerpt, and is named in the commit message or visible in its diff.

`selection.candidates` lists all 29 commits with the status and the reason for
every exclusion. The debate log is
`.project-toolkit/critique/ADR-100-101-enforcement-planes-debate-log.md`.

## Arms

| Arm | Input | What it tests |
|---|---|---|
| `unassisted` | Pre-fix ADR text only | A review with no repository access. |
| `assisted` | Pre-fix text plus the entry's evidence excerpts | A review whose verification was done. Only entries with evidence run. |
| `control` | Post-fix text | The false-flag floor. A role that matches here flags something the fix removed. |

Each role gets the repository's own Phase 1 prompt from
`.claude/skills/adr-review/references/agent-prompts.md`, with the Factual Claim
Verification block pasted in, and the role's `templates/agents/<role>.shared.md`
as the system prompt. The harness tells the role it has no shell or repository
access, so claims that need one come back UNVERIFIED.

## Scoring

No model judges another model. Each entry has a `match` rule: a list of groups,
each group a list of lowercase substrings. A finding matches when every group
has one substring in that one finding. Findings come from the Weaknesses/Gaps,
Scope Concerns, and Questions bullets, the Blocking Concerns rows, and the
Claims Checked rows marked REFUTED. UNVERIFIED claim rows are not findings: a
review with no repository access marks nearly every claim UNVERIFIED, and such
a row only repeats the ADR's wording beside a verdict cell.

Three strengths are reported per cell:

- **Mentioned**: the full response names the defect's subject (an entry's
  `topic` substrings) anywhere. This is context, not a catch. It separates a
  role that never looked at the area from one that looked and did not diagnose.
- **Flagged**: some finding matches the rule.
- **Blocked**: a matching finding is a P0 or P1 Blocking Concern or a REFUTED
  claim. This is the strength that stops a real review.

Each hit stores the matching finding text in `matched`, and each row stores the
SHA-256 of the full response, so a reader can audit any hit or miss. The unit
tests check that every rule fires on its own defect statement and that no rule
contains a one-character substring.

Errored calls count toward `errors`, never toward `n`, so a failing provider
cannot lower a rate by looking like a miss. Intervals are 95 percent Wilson
score intervals.

`--rescore --checkpoint rows.jsonl` re-scores stored responses with the current
rules and makes no model call, so a rule fix never needs a new run. The
checkpoint holds whole responses; a row whose stored text is cut short is
treated as unfinished and is retried.

## Run

```bash
uv run python scripts/eval/eval_adr_review_catch_rate.py --validate-corpus --arms unassisted,assisted,control
EVAL_PROVIDER=claude-cli uv run python scripts/eval/eval_adr_review_catch_rate.py \
    --arms unassisted,assisted --workers 6 \
    --checkpoint rows.jsonl --output results.json --report report.md
```

`--checkpoint` makes a run resumable. `--report-from results.json` re-renders
a saved report.

## Limits

- **Early rounds are under-sampled.** Commits typed `docs` that also corrected a
  defect (for example the agent-runtime credential inventory in 580f8a16e) are outside the rule. The
  corpus tilts toward the later, subtler defects of rounds 7 to 11, so it likely
  understates the catch rate on easier defects.
- **The replay is single-turn.** A real panel runs as agents with tools and
  several rounds. The `assisted` arm approximates verification by handing over
  the excerpt, which also makes the defect easier to see than a live search
  would.
- **Keyword rules can miss a correct finding phrased another way.** They can
  also match a finding that names the right words without the right point. The
  stored `matched` text is the audit trail, and the rules are conservative by
  design, so a rate here is closer to a floor than a ceiling.
- **The defects were found by this panel family.** The corpus is built from
  defects the debate surfaced, so it cannot measure defects the panel never
  finds. It measures whether a fresh single pass would have found the ones it
  eventually did.
- **One model, one trial per cell** unless the run says otherwise. The report
  lists the model and the trial count.
