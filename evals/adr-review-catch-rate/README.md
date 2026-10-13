# adr-review catch-rate harness

Measures how often each adr-review role flags a defect that the ADR-100/101
debate later fixed. ADR-101 abandons its Phase 2 unless a published per-role
catch rate justifies it (issues #5247 and #5248). This directory holds the
corpus, the method, and the results. The repository owner judges whether a
number is enough. The harness only produces the number.

## Question

If the six adr-review roles had reviewed the ADR text as it stood before each
fix, how many of them would have flagged the defect?

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
Claims Checked rows marked REFUTED or UNVERIFIED.

- **Flagged**: some finding matches.
- **Blocked**: a matching finding is a P0 or P1 Blocking Concern, or a REFUTED
  claim. This is the strength that stops a real review.

Each hit stores the matching finding text in `matched`, and each row stores the
SHA-256 of the full response, so a reader can audit any hit or miss. The
unit tests check that every rule fires on its own defect statement and that no
rule contains a one-character substring.

Errored calls count toward `errors`, never toward `n`, so a failing provider
cannot lower a rate by looking like a miss. Intervals are 95 percent Wilson
score intervals.

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
