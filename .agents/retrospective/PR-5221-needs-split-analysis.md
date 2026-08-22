# PR #5221 `needs-split` / commit-limit Analysis

**Trigger**: The push-time `push-ref-policy` gate blocked a push at 48 commits
against a 40-commit active limit (raised from the default 20 after this
branch's first qualifying merge of `origin/main`). Per `CONTRIBUTING.md`
"Bypassing the Limit," the `commit-limit-bypass` label is human-only; this
document is the prescribed AI-agent retrospective for a PR carrying
`needs-split`.

## Commit breakdown (`git rev-list --count HEAD ^origin/main` = 48)

| Category | Count | Share |
|---|---:|---:|
| `docs(sessions)`: session-log content + `endingCommit` follow-up commits | 18 | 38% |
| `docs(qa)`: QA report `qaCommit` rebind commits | 9 | 19% |
| `docs(architecture)`: ADR-102 corrections across three review rounds | 6 | 13% |
| Catch-up merges of `origin/main` | 5 | 10% |
| `test(qa-binding)` | 3 | 6% |
| Everything else (one commit each: `style(validation)`, `fix(validation)`, `fix(tests)`, `fix(session)`, `fix(qa-report)`, `fix(ci)`, `docs(critique)`) | 7 | 15% |

## Why so many commits: two amplifying mechanisms, not scope creep

1. **The session-log/QA-evidence bookkeeping pattern doubles or triples every
   review-response cycle.** `.claude/rules/session-logs.md` MUST 2 requires
   `endingCommit` to be set in a commit separate from the content change it
   describes. ADR-096's staleness contract (`post_qa_code_changes()`) then
   requires `qaCommit` to be rebound whenever any non-evidence path changes
   after it, which is every content commit. So one real fix in this PR
   costs: 1 content commit + 1 `endingCommit` follow-up + 1 `qaCommit`
   rebind = 3 commits minimum, before counting the fix itself. Across three
   rounds of automated (Copilot, Cursor Bugbot, `ai-spec-validation`) review
   plus manual diagnosis of CI failures, this pattern alone accounts for 27
   of the 48 commits (`docs(sessions)` 18 + `docs(qa)` 9 = 27, 56%).

2. **Upstream churn during a long review window.** `origin/main` advanced
   five times while this PR was in flight (PR #5219, two PYSEC pip-pin
   fixes, ADR-100/101, PR #5227's repo-wide ruff cleanup), each requiring a
   catch-up merge per `.claude/rules/ci-scripts.md` MUST 14 to avoid a false
   regression report. Each merge also forces one more `qaCommit` rebind
   (already counted above).

The remaining ~15% is the actual substantive work: the `QaBinding` identity
bug fix, the fallback-path ADR correction, the disagreement-warning wiring
test, and the debate-log staleness fix, each responding to a genuine,
independently verified review finding (see PR #5221's review-thread replies
for the verification record on each one).

## Is this one atomic change or several that should split?

**One atomic change.** The PR is a single validator-behavior change
(`session_qa_binding()`'s equality raise, ADR-102) plus its mandatory
governance trail (the ADR, its three-round debate log, the code, and the
tests). `.claude/rules/ci-scripts.md` MUST-NOT-2 requires the ADR and
implementation to land together; splitting the ADR from the code it accepts
would leave either half unreviewable on its own. The bookkeeping and
catch-up-merge commits cannot be split into a separate PR either, since they
exist only to keep this PR's own session log and QA evidence valid.

## Recommendation

Bypass, not split. The commit count is a direct, mechanical consequence of
this repo's own required audit-trail mechanics operating across an
unusually long, multi-round review window, not an unrelated-work bundle.
Splitting would not reduce total commits, would break the ADR-implementation
pairing MUST-NOT-2 requires, and would multiply the QA-rebind bookkeeping
across more PRs rather than eliminating it.

**Separately worth flagging as a process gap** (not blocking this PR): the
session-log + QA-rebind pattern scales linearly with review rounds on any
PR that carries a session log through multiple automated-review cycles. A
PR hitting three review rounds from three different bots is not a rare
event in this repo's current CI setup. If that recurs, the 40-commit limit
will recur with it independent of any contributor's behavior.

## Failure Mode Classification

**Class**: **Class 2 (Continuation Reset After Compaction)**, nearest existing
match, assigned per `.claude/rules/retros.md` MUST 2 rather than left
unclassified. The fit is partial and stated honestly: Class 2 describes agents
*losing track* of in-progress work across a long session; here the agent
correctly tracked and committed every required bookkeeping step throughout,
which is why the count grew rather than why work was lost. The shared shape is
narrower than the class name suggests: both are long-session state-accumulation
patterns, one from lost tracking, one from mechanically correct tracking that a
downstream policy (the commit-count ratchet) was not designed to absorb. No
existing class in `.agents/governance/FAILURE-MODES.md` describes "correct,
compliant agent behavior that mechanically accumulates against a fixed
threshold" as its own pattern; if this recurs (see the process-gap flag below),
that gap is worth a proposed new class via a linked ADR rather than continuing
to force-fit Class 2.

## Evidence

| Artifact | Link |
|----------|------|
| PR under analysis | [#5221](https://github.com/rjmurillo/ai-agents/pull/5221) |
| Commit-limit policy | `scripts/validation/pr_commit_count.py`, `.claude/rules/ci-scripts.md` MUST 14 |
| Session-log endingCommit rule | `.claude/rules/session-logs.md` MUST 2 |
| QA-rebind staleness contract | ADR-096 `post_qa_code_changes()` |
| Push-time gate that triggered this analysis | `push-ref-policy` hook (Lefthook) |

## Remediation

| Action | Owner | Status |
|--------|-------|--------|
| Apply `commit-limit-bypass` label to unblock PR #5221 | Human reviewer | Pending |
| Consider raising the post-merge limit or exempting bookkeeping-only commits in a future ADR | Process owner (TBD via issue) | Not started |
| No code or governance change required for this specific PR | n/a | N/A |
