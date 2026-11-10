# ADR-041 amendment 2026-11-09: /review CodeQL caller rules

This file holds the full rule set for the ADR-041 amendment "Let /review read
CodeQL results as an explicit caller". The ADR states the decision and links
here, because the record is held to a 500-line cap. The rules below are part of
that decision. The debate that produced them is in
`.project-toolkit/critique/ADR-041-debate-log-2.md`.

Changing this file changes the ADR-041 decision. Any edit here goes through the
same adr-review debate as an edit to the ADR itself, with a new debate log.

## Full amendment text

Status of this amendment: Accepted 2026-11-09. The adr-review debate
(`.project-toolkit/critique/ADR-041-debate-log-2.md`) shaped this text. Round 1
blocked a first draft that ran a cached local scan.

Problem. The `security` agent has no Bash tool, and `security-review` reads a
diff without running anything. A reviewer never sees CodeQL's semantic findings
during `/review`, even though Tier 1 already computes them for every pull
request (`.github/workflows/codeql-analysis.yml`, `pull_request` trigger,
`upload: true`).

Change. `/review` becomes one explicit caller of CodeQL results, only when its
`security` axis is selected. It is the only new caller; `security-review` and
the `security` agent are unchanged.

Scanner-input guard (applies before either source). The diff is merge-base with
the default branch to HEAD, plus any uncommitted change. If it touches
`.codeql/**`, `.github/codeql/**`, `.github/workflows/codeql-analysis.yml`,
`.github/actions/**` (composite actions the workflow calls), or the
`codeql-scan` skill scripts, the step reports
`CodeQL: SKIPPED (scanner inputs modified)` and reads no result. A branch must not
be able to change the code that scans it, or the config and queries that decide
what it reports, and then have that result trusted.

Sources, in this order:

1. **Tier 1 alerts (preferred).** When the reviewed branch has an open pull
   request, read its code-scanning alerts through the GitHub API with GET
   requests only, using a token with read access to code scanning alerts. No
   scanner, script, or binary from the branch runs on the reviewer's machine.
   - Tier 1 analyzes the pull request merge ref. An analysis counts as current
     when its ref is that merge ref, the pull request head SHA it analyzed
     equals the reviewed HEAD, and the working tree is clean. Otherwise the step
     reports `CodeQL: STALE (analyzed <sha>, reviewing <sha or working tree>)`.
     The analysis record stores the merge commit SHA, so the implementation
     derives the analyzed head SHA from that merge commit (its pull request
     head parent) and tests that step.
   - No analysis for the ref (for example the workflow's path filter skipped
     it) reports `CodeQL: NOT ANALYZED`.
   - Alerts are read page by page until the API reports no next page. An
     authorization or not-found error, or paging that cannot complete, reports
     `CodeQL: SKIPPED (<reason>)`. A partial read is never treated as complete.
2. **Local Tier 2 scan (fallback, before a pull request exists).** Allowed only
   when every guard below holds. If any guard fails, the step reports
   `CodeQL: SKIPPED (<guard>)` and runs nothing.
   - The CodeQL CLI and the `.codeql/` directory both exist, checked before the
     call. Absence is a skip, never inferred from an exit code.
   - The working tree is clean, and the database cache was built at the
     reviewed HEAD. The cache is keyed on HEAD and config only, so any
     uncommitted change makes a cached result stale.
   - The step runs the documented wrapper with `--operation quick --ci`, a 60
     second limit, and an environment limited to `PATH`, `HOME`, `LANG`, and
     `TMPDIR`. On timeout it kills the whole process group.
   - The result is `CLEAN` only when at least one language was detected and the
     run wrote a SARIF file for each detected language after the run started.
     Exit 0 with a skip marker, exit 2 or 3, any other exit code, a signal, or a
     timeout is `SKIPPED`.

Rules for both sources:

- **Explicit.** Only a `/review` invocation starts it. No hook, edit event, or
  schedule does. An unattended `/review` (for example one run by `/ship` in a
  headless session) may use source 1 only, never the local scan.
- **Untrusted data.** Results reach the `security` axis as rule id, a
  repository-relative path checked against the diff, and a line number. A rule
  id is passed only if it matches `^[A-Za-z0-9/_.-]{1,100}$`; others are counted
  and dropped. No free-text message or rule name from the results is passed.
- **Scoped.** A result is attached when any location in it (primary location,
  related locations, or code-flow steps) is in a file the diff touches. Other
  results are counted by file and not attributed to this change.
- **Input only.** A CodeQL result never sets the verdict by itself. The
  `security` axis confirms or rejects each one against the diff. Tier 1 stays
  the only blocking gate.
- **Loud.** `STALE`, `NOT ANALYZED`, and `SKIPPED` are named in the review output
  and are never reported as clean.

What this amendment does NOT change:

- Tier 1 (CI/CD) is still the blocking gate on every PR.
- Automatic scanning during edits stays retired. No edit-time trigger is added,
  and #3219 remains the design target for one.
- The scanner's behavior, configs, and exit codes (ADR-035) are unchanged.
  Routing and capability metadata in the `codeql-scan` skill may change to name
  `/review` as a caller.
- Tier 2 remains optional. A developer without the CLI is not blocked.

Alternatives considered. A cached local scan as the only source was rejected in
round 1: the cache is keyed on HEAD, so it either reports stale results as clean
or rebuilds cold and exceeds the 60 second budget, and it runs branch-controlled
code. Wiring `security-review` as a second caller was rejected to keep one caller
and to avoid changing that skill's eval input.

Consequence for the investment policy. Tier 2 moves from "Maintenance-Only" to
"Maintenance plus this single caller". It does not return to Active Development.
Review by 2027-05-09 (`review-by` in the frontmatter). `/review` keeps no run
record, so on that date the local fallback is removed by default, unless someone
cites a `/review` output in which the fallback produced a `CLEAN` or findings
result. Source 1 stays.

