# Skill Sidecar Learnings: pr-review

**Last Updated**: 2026-05-03
**Sessions Analyzed**: 1 (PR #1873, 5-round /pr-review iteration)

## Constraints (HIGH confidence)

- **Disable or coordinate with deferred remote /pr-review routines before
  iterating locally.** A scheduled remote routine racing local edits caused 4
  of 5 rounds to need `git reset --hard origin` + cherry-pick reconciliation.
  Symptoms: `git push` rejected, conflicts on duplicate same-named exception
  classes, identical fixes shipped from both sides. Mitigations: (1) do not
  schedule a remote /pr-review while planning local edits, OR (2) commit and
  push immediately after each fix to minimize the divergence window. (Session
  PR #1873, 2026-05-03)

- **Verify bot-flagged claims at byte level before fixing.** Copilot raised
  false positives in this session: an em-dash claim on a line with 0
  em-dashes (verified with `python3 -c "data.count(b'\xe2\x80\x94')"`); a
  `|| Metric |` table claim on rows that `cat -A` showed have a single `|`.
  Adopt a verification step: `grep -P` for the unicode char or `cat -A` the
  exact line before any cosmetic edit driven by a bot flag. (Session PR
  #1873, 2026-05-03)

## Preferences (MED confidence)

- **PR template `## Changes` section requires bullets immediately after the
  heading.** `validate_pr_description.py` regex
  `(?ms)##\s+Changes\s*\n+(?!##)\s*[-*]` requires a `-` or `*` bullet line
  before any `###` subheader. A body that goes straight from `## Changes` to
  `### Final result (...)` produces a Template Compliance WARN (3/4
  sections). Always add a top-level `-` bullet summary first; subsections
  may follow. (Session PR #1873, 2026-05-03)

- **Em-dash policy is sweep-style, not file-by-file.** Project doc style at
  `.agents/steering/documentation.md` lines 221-229 forbids em/en dashes.
  When this applies, run a single audit
  (`grep -rln $'—' <dirs>` or a Python byte-count) and fix all matches
  in one commit batch. Per-file flags from review bots (Copilot in
  particular) will arrive across multiple rounds otherwise. (Session PR
  #1873, 2026-05-03 — fix landed across rounds 3-4)

- **Adapter ↔ runner contracts must be coordinated.** When changing an
  exception ↔ typed-result contract at one side of a boundary, audit every
  catch site on the other side. Concrete instance: remote commit `0df0f324`
  changed `AnthropicAPIAdapter.call_model` to return
  `APICallResult(error_category="auth")` instead of raising `RuntimeError`,
  but did not update the runner. The runner's
  `if "ANTHROPIC_API_KEY" in str(exc)` catch became dead code; `EXIT_AUTH`
  was unreachable. Fix landed in commit `0ba277c4`. (Session PR #1873,
  2026-05-03)

- **Archive evidence: won't-fix with rationale.** Files under
  `evals/_archive/` are preserved verbatim per the policy in their parent
  ADR (in this session, ADR-058 §"v1 invalidation"). Reply to bot findings
  on those files with archive-by-policy citation; do not modify the file.
  Five archive-targeted findings closed this way in round 1. (Session PR
  #1873, 2026-05-03)

## Edge Cases (MED confidence)

- **Test count drift after pulling remote commits.** The remote /pr-review
  routine added tests independently. Local count went 94 → 123 → 126 → 127
  across rounds. After `git fetch` + `git reset`, re-run pytest before
  asserting "no regressions." (Session PR #1873, 2026-05-03)

- **Bot misclassification of pipe-delimited Markdown tables.** When a row
  starts with `|` and the previous line is also a `|`-delimited row,
  Copilot can misread the row as `|| ...`. This is a render-side artifact,
  not a file content issue. Verify with `cat -A` before "fixing." (Session
  PR #1873, 2026-05-03)

## Notes for Review (LOW confidence)

- **Round-over-round comment count converged 19 → 5 → 8 → 7 → 1 across 5
  rounds.** Convergence is the expected shape of /pr-review iteration on a
  large PR (51 files, 8K added lines). Roughly 5 rounds to clean for a PR
  of that size, mostly noise after round 3. (Session PR #1873, 2026-05-03)
