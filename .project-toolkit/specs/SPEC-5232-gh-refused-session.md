# SPEC: A session that refuses gh is a supported mode (issue #5232)

Status: accepted after debate (critic, independent-thinker). Counts and line numbers are anchored to `e8fe2a9c1` on 2026-11-04.

## Step 0 First Principles

### Q1 Demand Reality

The repository owner asked for this on 2026-11-04: the Claude GitHub App will not be connected to the organization, so the check must be rethought. The second requester is issue #5232 itself, filed from a cloud session that hit the 403.

### Q2 Status Quo

An agent in a cloud session runs `check_github_transport.py` and gets `Transport: gh_unusable`. It then works through the GitHub MCP tools. At the end of `/pr-review` it must not run `run_completion_gate.py`, because every verifier exits non-zero and the gate prints FAIL for all five criteria. The skill text tells it to check each criterion by hand. If it runs the gate anyway, the output says the PR failed. The issue stays open and `blocked:human`, waiting for an admin action that will not happen.

Reframing: automation only.

### Q3 Desperate Specificity

An agent running `/pr-review` or `/pr-autofix` in a cloud session. It is blocked on telling "the PR failed a criterion" apart from "this session cannot read GitHub".

### Q4 Narrowest Wedge

About 3 hours: `run_completion_gate.py` reports a criterion it could not verify in a refused session as unknown, the refusal message stops presenting the App connection as the fix, and `transport-routing.md` states the policy.

### Q5 Observation

- `run_completion_gate.py:3744-3749` sets `passed = fail_open` on any non-zero verifier exit. All 5 criteria in `pr-review-config.yaml:210-253` set `fail_open: false`.
- The github skill says "A transport failure is an unknown, never a verdict." The gate contradicts that.
- ADR-099 and ADR-100 record two sessions where a gate that failed closed on this 403 caused a stacked PR and a 33-commit squash with a force-push.
- Issue #5232 was triaged `blocked:human` on 2026-10-17 with no agent-fixable path.

### Q6 Future-fit

The policy gets cheaper as gates grow: one rule covers every new gate. The risk is the probe's match on the proxy body. A changed body would become FAIL, which is the safe direction.

## Step 0.5 Prior Art

- ADR-099 removed the commit cap gate because it could not verify its own relief in this session class.
- ADR-100 "Two different 403s": the GraphQL body is a query allowlist and the REST body is the account-level denial.
- Issue #5693 added `GRAPHQL_BLOCKED` and exit 2 for refusals, because a refused session has no reset and exit 3 would invite retries.
- `src/claude/skills/github/references/transport-routing.md` already maps each script to an MCP operation.
- Chesterton's fence on `fail_open: false`: the gate docstring cites the PR #1887 retrospective. "A verifier that cannot verify must not be silently treated as having verified." This spec keeps that fence.

## Problem statement

Issue #5232 assumes an admin fix that the owner has declined, so `gh` stays refused in cloud sessions for this organization. The transport preflight already handles that, but the completion gate reports the refusal as a failed PR, and the shipped message still names the App connection as the fix.

## Local gate inventory

Searched `lefthook.yml`, `scripts/validation/`, `.claude/hooks`, `src/claude/hooks`, `templates/hooks`, and the completion gate.

| Gate | On a proxy 403 | Change |
|---|---|---|
| `run_completion_gate.py` | Fails closed, reported as FAIL | Yes, this spec |
| `validate_no_orphaned_build_deferrals.py:171` | WARN | None |
| `active_plan_closeout.py:194` | Advisory | None |
| `spec_contradiction.py:145` | Skips the link check | None |
| `checks_common.py:255` | WARN, falls back to `@{u}` then `origin/main` | None |
| `git_hook_policy.py:9000` bot cascade | Always returns 0 | None |
| `testmon_seed.py:150` | Runs the full suite | None |

## Options

| Option | Result | Verdict |
|---|---|---|
| A. Keep waiting for the App | Issue never closes | Rejected by the owner |
| B. Drop the preflight | Every workflow pays a failed call and may retry a condition with no reset. Losing `gh_unusable` also loses MCP routing | Rejected |
| C. Fail open in the completion gate | A session that reads nothing reports a PR ready. This repeats the failure the PR #1887 retrospective named | Rejected |
| D. Use MCP inside the gate | A subprocess cannot reach MCP tools (ADR-099). Only the agent can | Not possible |
| E. Match refusal text in verifier output | Verifier output carries PR-controlled text, so a PR author could turn a FAIL into unknown and steer the agent to a hand check. It also copies the classifier | Rejected in debate |
| F. Run `check_github_transport.py` from the gate first | Reuses the classifier, but runs a work-tree script outside the verified closure (CWE-829) and aborts rows a GraphQL-only refusal would still serve | Rejected in debate |
| G. Keep the preflight. After a verifier exits non-zero, the gate runs a fixed `gh` probe and reads the proxy's answer | Evidence comes from the environment, not from PR text. No work-tree code runs. Healthy passing runs pay nothing | Recommended |

## Debate log

- Critic: REVISE. Accepted: exit 2 collides with the config contract, match scope was undefined, `fail_open` rows were under-specified, mirrors and tests were unnamed. Declined: splitting the message rewording into its own PR, because the pattern no longer depends on that text. Declined: a `verify_config_only_exits` row, because that mode dispatches nothing.
- Independent-thinker: replace text matching with an up-front check. Accepted the objection to a second classifier and to PR-influenced text. Declined running the preflight script, because of the trust boundary. Declined dropping per-row results, because a GraphQL-only refusal can leave REST verifiers working.
- Both preferred exit 3 over exit 2.
- `/review` round 1 merged WARN. Accepted from security, qa, reliability, and correctness: exit 1 is an answer and stays failed. Accepted: the GraphQL body explains only exit 2, the probe reuses the `check_gh_auth` query, an inconclusive probe prints a note, and the stderr line separates unknown from a trust halt. Accepted from architect: record the decision in an ADR (ADR-120). Declined: passing `cwd=_PROJECT_ROOT` to the probe, because verifiers inherit the same cwd and must agree with it.

## User stories

- As an agent in a refused session, when I run the gate I see `unknown` per criterion and a pointer to the hand check, so I do not report a healthy PR as failed.
- As an owner, I can read one section that says which gates may depend on `gh`.
- As a consumer of this toolkit whose org did connect the App, nothing changes for me.

## Ontology

- **Session refusal**: a verifier failed because the environment refused GitHub or a GraphQL query. Not a statement about the PR.
- **Criterion status**: `passed`, `failed`, or `unknown`.
- **Gate verdict**: `pass`, `fail`, or `unknown`. `fail` wins over `unknown`.

## Data model

Each row keeps `passed` and gains `status`. The payload keeps `all_passed` and gains `verdict` and `unknown_criteria`. Only a row with `passed: false` and a verifier exit above 1, or `api_error: true`, can become `unknown`. A `fail_open: true` row that passed stays `passed`, because its author accepted that outcome.

## Integrations

The gate calls the `gh` on PATH directly, with two fixed queries: `gh api repos/{owner}/{repo}` and a GraphQL viewer query. It reads only a failed call's output. The REST call matches `GitHub access is not enabled for this session`, and the GraphQL call matches `GraphQL query is not enabled for this session`. The gate does not read the preflight's verdict. If the skill text is ignored and the gate runs in a refused session, it reports unknown rather than failure.

## Failure modes

| Mode | Result |
|---|---|
| Proxy changes its wording | Rows read FAIL, as today. Safe direction |
| PR text in verifier output resembles a refusal | Ignored. Verifier output is never matched |
| Probe cannot run (no `gh`, timeout, no repo) | No evidence, so rows read FAIL, as today |
| Viewer query served, repository GraphQL refused, repository REST served | Rows read FAIL, as today |
| Viewer query served, repository calls refused | Rows read `unknown` (criterion 17) |
| `gh` cannot fill `{owner}/{repo}` from the remote | REST probe gives no evidence. The GraphQL probe still catches a refused viewer query. If the viewer query is served, rows read FAIL, the safe direction |
| Verifier exits 1 with a real finding in a refused session | Stays `failed`. Exit 1 is an answer under ADR-035 |
| GraphQL-only refusal beside a retryable exit 3 | Stays `failed`. The narrow body refuses one query shape |
| A definite failure beside a refusal | Verdict `fail`, exit 1 |
| Verifier exits 0, bad JSON or false `pass_when`, no `api_error` | Unchanged, FAIL |

## Security

No PR-controlled value reaches the probe's argv, and no work-tree script runs, so the verified closure does not change. On Windows a bare `gh` lookup can search the cwd. `_run_git` already shares that residual. The invariant: a refusal never produces `all_passed: true` or exit 0 for a fail-closed criterion.

## Observability

Row `status`, payload `verdict`, and the evidence file written by `--evidence-path` show the result. The table prints `UNKN` for those rows, plus one line naming the hand check.

## Acceptance criteria

1. When the REST probe observes the session body, the gate shall set rows that exited 2, 3, or 4 to `unknown`. When only the GraphQL probe observes a refusal, it shall set only rows that exited 2 to `unknown`. Each keeps `passed: false`.
2. When the probe observes no refusal, or cannot run, the gate shall leave every row `failed`, as today.
3. The gate shall run at most one pass over the probes per run, and none when no verifier exited above 1 or reported `api_error: true`.
4. The gate shall never take refusal evidence from verifier output. A verifier that prints refusal text while exiting non-zero in a served session stays `failed`. The gate reads one verifier field, `api_error`, and only to decide whether a row can read unknown.
5. A row that exited 1, or failed through `pass_when` or bad JSON at exit 0 without `api_error: true`, shall stay `failed` in a refused session. That includes `fetched_pages_complete: false`, which a PR can cause through a thread with over 100 comments or the page cap.
6. When any row is `failed`, the gate shall report verdict `fail` and exit 1.
7. When no row is `failed` and at least one row is `unknown`, the gate shall report verdict `unknown`, list those rows in `unknown_criteria`, and exit 3.
8. The gate shall never exit 0 or report `all_passed: true` while a row is `unknown`.
9. `_print_table` shall mark an unknown row `UNKN` and keep its evidence lines. The gate shall print a stderr line starting `UNKNOWN:` that names the hand check, in table and JSON modes.
10. `_TRANSPORT_BLOCKED_MESSAGE` shall stop presenting the App connection as the expected fix and shall name MCP as the supported path.
11. `transport-routing.md` shall state that a blocking local gate must not depend on `gh` for its verdict, and that a gate unable to verify reports unknown.
12. `pr-review` and `pr-autofix` shall document exit 3 with verdict `unknown`, route it to the hand check, and say not to retry it. Exit 3 with no payload stays the trust halt. `gh_unusable` also covers a missing `gh`, where the gate exits 1, so the `pr-review` hand-check rule applies to any non-pass result.
13. All harness mirrors shall be regenerated with `build_all.py`.
14. ADR-120 shall record the unknown verdict and its exit code, and ADR-059 Decision 1 shall point to it. ADR-059 is at the 500-line cap, so it cannot hold an amendment.
15. Every shipped criterion's verifier shall call `assert_gh_authenticated` before reading PR data, pinned by a test.
16. A hand check shall never set `all_passed` or arm a merge.
17. A row at exit 0 with `api_error: true` shall count as exit 3 for criterion 1. `get_unresolved_review_threads.py` shall set that field only when a `gh` call raised. A session with the viewer query served and repository calls refused then reads `unknown`, not `fail`.

## Out of scope

- Any change to `check_github_transport.py` verdicts.
- Rate limits and missing `gh`: they keep their current gate result.
- The six advisory gates in the inventory.

## Deferred

- Feeding MCP-read evidence into the gate so a refused session gets a machine verdict. Owner: repository owner, if the hand check proves too costly.
- Caching the refusal in `checks_common.py:_gh_base_ref`. It costs one failed call per lookup and is not a correctness issue.

## Open questions

None.

## CVA summary

Common: every verifier either returns JSON or fails. Varies: why it failed. The gate needs one new distinction, measured by the gate itself, not a new verifier contract.

## Buy-vs-build decision

N/A (bug fix / doc / refactor).

## Complexity classification

Tier 3, because it changes a shared exit contract on a trust boundary. Clear domain. Standard lifecycle after this spec.
