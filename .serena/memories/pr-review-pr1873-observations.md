# Skill Sidecar Learnings: pr-review

**Last Updated**: 2026-05-03
**Sessions Analyzed**: 1 (PR #1873, 5-round /pr-review iteration)

## Constraints (HIGH confidence)

- **Disable or coordinate with deferred remote /pr-review routines before
  iterating locally.** A scheduled remote routine racing local edits causes
  push rejection and rebase conflicts on duplicate fixes. Mitigations:
  (1) do not schedule a remote /pr-review while planning local edits, or
  (2) commit and push immediately after each fix to minimize the
  divergence window. (Session PR #1873, 2026-05-03)

- **Verify bot-flagged claims at byte level before fixing.** Copilot raised
  false positives in this session: an em-dash claim on a line with 0
  em-dashes; a `|| Metric |` table claim on rows that `cat -A` showed have
  a single `|`. Verification one-liner that actually runs:
  `python3 -c 'import sys; print(open(sys.argv[1], "rb").read().count(chr(0x2014).encode("utf-8")))' path/to/file.md`
  for em-dashes (U+2014); swap `0x2014` for `0x2013` to count en-dashes.
  Or `cat -A path/to/file.md` for table-rendering claims. Verify before
  any cosmetic edit driven by a bot flag. (Session PR #1873, 2026-05-03)

## Preferences (MED confidence)

- **PR template `## Changes` section requires bullets immediately after the
  heading.** See `github-pr1873-observations.md` Preferences section for the
  authoritative regex pattern and behavior documentation. A body that goes
  straight from `## Changes` to `### Final result (...)` produces a Template
  Compliance WARN (3/4 sections). Always add a top-level `-` bullet summary
  first; subsections may follow. (Session PR #1873, 2026-05-03)

- **Em-dash policy is sweep-style, not file-by-file.** Project doc style
  at `.agents/steering/documentation.md` (Formatting Violations table,
  lines 220-228) forbids em/en dashes. Run one audit and fix all matches
  in a single commit; otherwise per-file bot flags (Copilot in
  particular) arrive across multiple rounds. Audit one-liner (uses
  ripgrep, the project's default search tool; its default Rust
  regex engine supports Unicode escapes like `\x{2014}` and avoids
  the `grep -P` portability gap on BSD systems. PCRE2 in `rg` is
  opt-in via `-P` and not needed here):

  ```bash
  rg -l '\x{2014}' <dirs>   # em-dashes (U+2014)
  rg -l '\x{2013}' <dirs>   # en-dashes (U+2013)
  ```

  (Session PR #1873, 2026-05-03; fix landed across rounds 3-4)

- **Adapter to runner contracts must be coordinated.** When changing an
  exception-vs-typed-result contract at one side of a boundary, audit
  every catch site on the other side. A typed-result conversion that
  leaves the old exception catch in place produces dead code (the
  caller never enters the catch) and silently breaks downstream exit
  codes that depended on it. (Session PR #1873, 2026-05-03; concrete
  instance preserved in the session log)

- **Archive evidence: won't-fix with rationale.** Files under
  `evals/_archive/` are preserved verbatim per the policy in their parent
  ADR (in this session, ADR-058 §"v1 invalidation"). Reply to bot findings
  on those files with archive-by-policy citation; do not modify the file.
  Five archive-targeted findings closed this way in round 1. (Session PR
  #1873, 2026-05-03)

## Edge Cases (MED confidence)

- **`git reset --hard origin` is not a valid reset target.** `origin`
  is a remote name, not a commit-ish; the command exits non-zero with
  `fatal: ambiguous argument 'origin': unknown revision or path not in
  the working tree`. Use `git reset --hard @{u}` (the tracked upstream)
  or `git reset --hard origin/<branch>` (named ref). (Session PR
  #1873, 2026-05-03)

- **Test count drift after pulling remote commits.** The remote /pr-review
  routine added tests independently. Local count went 94, 123, 126, 127
  across rounds. After `git fetch` + `git reset`, re-run pytest before
  asserting "no regressions." (Session PR #1873, 2026-05-03)

- **Bot misclassification of pipe-delimited Markdown tables.** When a row
  starts with `|` and the previous line is also a `|`-delimited row,
  Copilot can misread the row as `|| ...`. This is a render-side artifact,
  not a file content issue. Verify with `cat -A` before "fixing." (Session
  PR #1873, 2026-05-03)

## Notes for Review (LOW confidence)

- **Round-over-round comment count converged 19, 5, 8, 7, 1 across 5
  rounds.** Convergence is the expected shape of /pr-review iteration on a
  large PR (51 files, 8K added lines). Roughly 5 rounds to clean for a PR
  of that size, mostly noise after round 3. (Session PR #1873, 2026-05-03)
