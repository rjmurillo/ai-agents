# ADR-041 Debate Log 2: /review as an explicit CodeQL caller

**ADR**: `.project-toolkit/architecture/ADR-041-codeql-integration.md`
**Amendment**: "Amendment 2026-11-09: Let /review read CodeQL results as an explicit caller"
**Rules file**: `.project-toolkit/analysis/adr-041-review-caller-rules.md`
**Prior debate log**: `.project-toolkit/critique/ADR-041-debate-log.md` (closed 2026-01-16)
**Review date**: 2026-11-09
**Protocol**: adr-review, full six-agent panel. The amendment changes the Tier 2
investment policy ("Maintenance-Only"), which other gates read.
**Participants**: architect, critic, independent-thinker, security, analyst, high-level-advisor

## Summary

Richard asked for CodeQL to be part of security review and chose to amend
ADR-041 before wiring it. The first draft let `/review` run the cached local
Tier 2 scan. Round 1 blocked it. The rewrite makes Tier 1 pull request alerts
the preferred source and keeps the local scan as a guarded fallback. Round 2
moved five reviewers to Disagree-and-Commit; security still blocked on a gap
that round 3 addresses.

## Phase 0: Related work

- The 2026-07-21 amendment retired automatic edit-time scanning and kept Tier 2
  as developer-initiated, maintenance-only (ADR-041, Operational Status table).
- PR #7165 removed the duplicate wrapper `invoke_codeql_scan_skill.py` and
  ported its git-missing fix into `invoke_codeql_scan.py`.
- `.github/workflows/codeql-analysis.yml` runs on `pull_request` with
  `upload: true`, so Tier 1 alerts exist for every pull request.

## Round 1 Summary

### Key Issues Addressed

- **P0 (all six reviewers): a stale cache can produce a false CLEAN.**
  `.codeql/scripts/invoke_codeql_scan.py:168-178` validates the cache on git
  HEAD and config only. A dirty working tree reuses a database built before the
  diff, and a new commit forces a cold rebuild that exceeds the 60 second
  budget.
- **P0 (security): branch-controlled code execution.** The wrapper runs
  `.codeql/scripts/` and the CLI from the branch under review, with the
  reviewer's environment, including tokens (CWE-829, CWE-94, CWE-522).
- **P0 (critic): exit 0 does not mean scanned.** The wrapper exits 0 when
  `.codeql/` is missing, and the delegate exits 0 when no languages are found.
- **P1:** SARIF text reaches the model as free text (prompt injection); a
  branch can edit `.github/codeql/codeql-config*.yml` to hide its own findings;
  status lines claimed the amendment before acceptance (ADR-073); the post
  deployment measure was not observable; the 60 second limit was not enforced;
  the amendment claimed one caller but the draft wired `security-review` too;
  the alternative of reading Tier 1 alerts was never considered.
- **P2:** file-only scoping drops data-flow findings; orphaned child processes
  on timeout; unlisted exit codes; an install hint that omitted `--add-to-path`.

### Major Changes Made

- Tier 1 pull request alerts became the preferred source, read-only.
- The local scan became a fallback guarded by a clean tree, a cache built at
  HEAD, a scanner-input guard, a scrubbed environment, a process-group kill on
  timeout, and `CLEAN` only with SARIF per detected language.
- Results limited to rule id, path, and line; any-location scoping.
- One caller only: `security-review` is not wired.
- Unattended runs use the alert source only.
- Status lines made conditional; a review-by date added.

### Agent Positions

| Agent | Position | Basis |
|---|---|---|
| architect | Block | False CLEAN from the HEAD-keyed cache |
| critic | Block | Rules 2 and 3 contradict; exit 0 is not a scan |
| independent-thinker | Block | Stale-cache premise; most runs would skip |
| security | Block | Branch-controlled code execution and token exposure |
| analyst | Disagree-and-Commit | Text mismatches with the code, fixable in text |
| high-level-advisor | Disagree-and-Commit | False CLEAN and two-caller scope must be fixed |

### Next Steps

Rewrite around Tier 1 alerts and re-vote.

## Round 2 Summary

### Key Issues Addressed

- **P1 (architect, independent-thinker, critic, high-level-advisor, analyst):**
  Tier 1 analyzes the pull request merge ref, so "analyzed commit equals
  reviewed commit" never holds and source 1 would always report `STALE`. It
  fails loud, never as a false CLEAN.
- **P1 (security): the scanner-input guard covered only the local fallback.**
  Tier 1 reads `.github/codeql/codeql-config.yml` from the pull request
  checkout, so a pull request can exclude its own paths or load a query pack
  whose rule names are attacker text (CWE-693, ASI01).
- **P1 (critic): zero detected languages could satisfy "SARIF for every
  detected language".**
- **P1 (critic): alert reads had no paging rule** (`lossless-queue-reads.md`).
- **P1 (analyst, high-level-advisor): the review-by rule depended on a count
  `/review` never records.**
- **P2:** no state for an unanalyzed pull request; old SARIF files could pass
  the `CLEAN` check; API errors had no outcome; the token scope was not named;
  the environment rule read as a denylist; the diff base was not named; the
  cited debate log did not exist yet.

### Major Changes Made

- The scanner-input guard now applies before either source, adds
  `.github/workflows/codeql-analysis.yml`, and names the diff base (merge-base
  with the default branch to HEAD, plus uncommitted changes).
- An alert analysis counts when its ref is the merge ref and the analyzed pull
  request head SHA equals the reviewed HEAD. `NOT ANALYZED` is its own state.
- Alerts are read page by page with GET requests only; API errors and
  incomplete paging report `SKIPPED`. The token scope is code scanning read.
- Rule ids must match `^[A-Za-z0-9/_.-]{1,100}$`; rule names and messages are
  never passed.
- `CLEAN` requires at least one detected language and SARIF written after the
  run started. The environment is an allowlist: `PATH`, `HOME`, `LANG`,
  `TMPDIR`.
- The local fallback is removed by default on 2027-05-09 unless someone cites a
  `/review` output where it produced a result. `review-by: 2027-05-09` is set
  in the frontmatter.
- The full rule set moved to
  `.project-toolkit/analysis/adr-041-review-caller-rules.md` because the ADR
  crossed the 500-line cap; the ADR keeps a normative summary and links it.

### Agent Positions

| Agent | Position | Basis |
|---|---|---|
| architect | Disagree-and-Commit | All round 1 issues resolved; merge-ref SHA match |
| critic | Disagree-and-Commit | Merge ref, zero languages, paging, review-by field |
| independent-thinker | Disagree-and-Commit | Merge ref; NOT ANALYZED state |
| security | Block | Scanner-input guard missing for source 1 |
| analyst | Disagree-and-Commit | Debate log path; unmeasurable removal rule |
| high-level-advisor | Disagree-and-Commit | Merge ref; removal rule needs a default |

### Next Steps

Round 3 vote on the revised text.

## Round 3 Summary

### Key Issues Addressed

- **Security round 2 Block resolved.** The scanner-input guard runs before both
  sources and covers the CodeQL workflow and the composite actions it calls.
- **P2 (architect, analyst):** the ADR summary said SARIF for "at least one
  language"; it now says every detected language, with at least one detected.
- **P2 (independent-thinker, high-level-advisor):** the analysis record stores
  the merge commit SHA. The rules file now says the implementation derives the
  analyzed head SHA from that merge commit and tests that step.
- **P1 (critic), held as dissent:** the binding rules file lives under
  `.project-toolkit/analysis/`, outside the adr-review trigger paths. Its header
  now states that any edit goes through adr-review. It was not moved under
  `architecture/`, because the lifecycle checks would then treat it as an ADR
  record.

### Major Changes Made

- Amendment status set to Accepted 2026-11-09; header line, Operational Status
  row, and frontmatter `date` updated; `docs/codeql-architecture.md` updated.

### Agent Positions

| Agent | Position | Basis |
|---|---|---|
| architect | Accept | Merge-ref match and debate log resolved |
| critic | Disagree-and-Commit | Rules file outside the reviewed record (dissent recorded) |
| independent-thinker | Accept | No P0 or P1 remains |
| security | Accept | Guard covers both sources; no new P0 or P1 |
| analyst | Accept | All round 2 items resolved |
| high-level-advisor | Accept | Strategic Review Verdict: APPROVED |

### Outcome

Consensus reached in round 3: 5 Accept, 1 Disagree-and-Commit. The amendment is
accepted. The wiring change is a separate pull request and must follow the rules
file, including a test for deriving the analyzed head SHA.

## Open questions settled

1. A CodeQL finding alone cannot set `CRITICAL_FAIL`. It is input that the
   `security` axis confirms or rejects. Unanimous.
2. The local fallback uses `--operation quick` within 60 seconds and only when
   the cache matches the reviewed HEAD. No full local scan is added; Tier 1 is
   the primary source.
3. `codeql-scan` stays `user-facing: false`. Unanimous.
4. The `security-review` eval re-run is not needed, because that skill is not
   changed. It becomes a merge condition only if a later change edits it.
