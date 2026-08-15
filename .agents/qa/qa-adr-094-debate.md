---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14712-b79742bf0-run-adr-094-multi-agent-debate.json
qaCommit: e137317ef468f70688671bd58f893273be52527f
---

# QA: ADR-094 adr-review debate log

## Scope

Two authored files: `.agents/critique/ADR-094-debate-log.md` (new) and a
9-line prose edit to `.agents/architecture/ADR-094-scoped-re-review-axes.md`.
No code, no generated artifact, no shipped skill change. The verifiable surface
is the gate contract, the factual claims in the debate log, and the repository
text rules.

## What ran

| Check | Command | Result |
|---|---|---|
| adr-review gate is satisfied | `git_hook_policy.py adr-review` via the `adr-review-policy` pre-commit job | PASS in 0.75s |
| Em-dash and en-dash prohibition (`.claude/rules/universal.md` MUST NOT 5) | Python count of U+2014 and U+2013 over both authored files | 0 and 0 |
| Banned vocabulary (`.claude/rules/voice.md`) | Python substring scan of the 19-word list over the debate log | 0 hits |
| Markdown lint | `markdown-autofix` and `markdown-check` pre-commit jobs | PASS |
| Session log parses and matches its filename number | `json.loads` plus `validate_session_json.py` | PASS |

## Claims verified against their sources

Every quantitative claim recorded in the debate log was re-measured by the
orchestrator before it was written, not taken from the reporting role.

| Claim | Command | Result |
|---|---|---|
| `/review` became a skill after the cited incidents | `git log --diff-filter=A -- .claude/skills/review/SKILL.md` | `c3ddc571a` 2026-05-24 |
| The SHA-bound marker landed after the cited incidents | `git log --diff-filter=A -- .../validate_review_marker.py` | `16c960418` 2026-06-04 |
| The 009 baseline reports two different signal ratios | `grep -n "52%\|24%\|182\|173" .agents/analysis/009-phase1-agent-comment-baseline.md` | `:163` 52% over 182 comments, `:178` 24% over 173 units |
| Marker census | `git log --all --format='%(trailers:key=Reviewed-By,valueonly)'` | 14 trailer commits, 3 full-set, 11 subset, 4 naming a `code-review` axis |
| No marker commit reached main | `git merge-base --is-ancestor <sha> origin/main` on sampled marker commits, plus a trailer count over `origin/main` | 0 on `origin/main`, all 14 on unmerged refs |
| `references/code-review.md` does not exist | `ls .claude/skills/review/references/` | 12 files, no `code-review.md` |
| No marker-writer script exists | `ls .claude/skills/review/scripts/` | `validate_findings_scope.py`, `validate_review_marker.py` only |

## Correction found and applied

One reporting role's headline measurement did not reproduce. The critic built
its P0-1 on "32 merged PRs carry a review marker on `origin/main`, mean 2.22,
median 1, max 8". `origin/main` carries zero such commits, because this
repository squash-merges and the empty marker commit is discarded. The number
was removed from the recorded finding and replaced with the reproducible form,
and the non-reproduction is documented in the debate log's own verification
section rather than dropped silently.

A second role's marker census was off by one in two counts (3 full-set not 4,
11 subsets not 10). Corrected against a direct count.

## Not verified

- **The PR #5059 and PR #5062 counter evidence** was supplied to this session as
  a narrative and was not independently reproduced from the PR record. The
  debate's engagement with it is conditional on that narrative being accurate.
- **The debate's forward-looking cost arithmetic** (49% with a security safety
  core, 37% on the late-round path) is arithmetic on the ADR's own assumed
  workload, not a measurement. No scoped mode exists, so no empirical figure is
  obtainable.
- **Whether the five P0 findings are individually correct** is the maintainer's
  call. This QA confirms each P0 cites a source that says what the finding
  claims; it does not certify that the recommended remediation is the right one.

## Verdict

PASS. The debate ran the six roles the skill specifies, reached no consensus,
recorded that honestly, and every number that entered the durable artifact was
re-measured first.
