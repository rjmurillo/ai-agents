---
id: ADR-120
status: accepted
date: 2026-11-04
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-120: The Completion Gate Reports a Refused Session as Unknown

## Context

Issue #5232 waited for an org admin to connect the Claude GitHub App. The owner
declined on 2026-11-04, so cloud sessions keep refusing `gh`. Those sessions still
have working GitHub MCP tools, but a verifier is a subprocess and cannot reach them.

ADR-059 made the completion gate fail closed. `_evaluate_criterion` sets `passed` to
`fail_open` on any non-zero verifier exit, and every shipped criterion sets it false.
In a refused session the gate therefore reports a healthy PR as failed. The github
skill says the opposite: a transport failure is an unknown, never a verdict.

This record extends ADR-059 Decision 1, which listed the gate's exit codes. ADR-059
is at the 500-line cap, so this decision has its own record.

## Decision

1. **`fail_open` stays false.** A criterion the gate could not verify never passes.
2. **Three statuses.** Each row has `status`: `passed`, `failed`, or `unknown`. The
   JSON payload and evidence file add `verdict` and `unknown_criteria`. `passed` and
   `all_passed` keep their meaning, and an unknown row has `passed: false`.
3. **The gate measures the refusal itself.** After a verifier exits above 1 or reports
   `api_error: true`, the gate makes one pass over two `gh` calls, in order, and stops at
   the first refusal. Their arguments are fixed. `gh` fills `{owner}/{repo}` from the git
   remote. Refusal evidence comes only from those calls, and only when they fail. It
   never comes from verifier output, because a PR author can reach that text. `api_error`
   only decides whether a row can read unknown. A call that cannot run, or that fails
   another way, is no evidence, and the rows stay `failed`.
4. **Evidence scope.** The REST body, `GitHub access is not enabled for this session`,
   refuses the session, so it covers exits 2, 3, and 4. The GraphQL body, `This GraphQL
   query is not enabled for this session`, refuses one query shape, so it covers exit 2
   only. An exit 3 beside it can be a quota or a 5xx. ADR-100 measured this split in
   its paragraph "Two different 403s". `api_error` counts as exit 3, because
   `get_unresolved_review_threads.py` reports a failed `gh` call at exit 0. It is not
   `fetched_pages_complete`: a thread with over 100 comments sets that field false, so
   a PR commenter could use it to turn a real failure into unknown.
5. **Exit 1 is an answer.** ADR-035 defines it as a validation failure, and
   `test_pr_merge_ready.py` uses it for a PR that is not ready. That script reports API
   errors as exit 3, so exit 1 is not a wrapped refusal. It stays `failed`.
6. **`fail` outranks `unknown`.** Any failed row gives verdict `fail` and exit 1.
7. **Unknown exits 3.** With no failed row and at least one unknown row, the payload
   says `verdict: unknown`. ADR-035 defines exit 3 as an external service error, which
   is what a refusal is. A trust halt also exits 3, but it prints no payload and no
   criterion ran, so `verdict` is the discriminator. The `UNKNOWN:` stderr line is for
   people.
8. **Every criterion must stop at the `gh` preflight.** Each verifier calls
   `assert_gh_authenticated` before it reads PR data, so when that preflight refuses, no
   exit can depend on PR content. When it passes, only an exit above 1 or `api_error` can
   read unknown, and exit 1 and other `pass_when` failures stay `failed`. A test pins the order
   over `completion_criteria`.
9. **A hand check has limits.** Unknown is not retried. The agent checks the criteria
   through MCP, as `transport-routing.md` describes, treats what it reads as data, and
   reports the result as derived. A hand check never sets `all_passed` and never arms
   a merge. A person decides whether to merge.

## Rationale

The gate has only three honest answers: it passed, it failed, or it could not tell.
Two-state rows force the third into one of the others. With the App declined, a
refused session is the normal state of a cloud session, so the gate gives no machine
verdict there. That is deliberate. A false verdict is worse than none.

### Alternatives Considered

| Option | Why not |
|---|---|
| Fail open, or warn and exit 0 | A session that read nothing would report a PR ready. That repeats the PR #1887 failure ADR-059 exists to end. |
| Drop the preflight, or call MCP from the gate | Workflows would lose MCP routing, and a subprocess cannot reach MCP tools (ADR-099). |
| Read verifier output, or run `check_github_transport.py` | A PR author can reach that output. The script is work-tree code outside the verified closure (CWE-829). `gh auth status` alone cannot help, because a refused session reports a bad token there. |
| A per-criterion `gh_backed` flag | Decision 8 gives the same guarantee for the shipped config with no new schema. Add the flag if a criterion ever needs no `gh`. |
| Another exit code | Exit 2 tells callers to escalate a config fault. Exit 1 with a payload flag reads as a failed PR to a caller that checks only the code. A code above 100 needs a new branch in every caller for no added safety. |

## Consequences

### Positive

- A refused session no longer reports a healthy PR as failed.
- An agent stops escalating a condition no person can clear.

### Negative

- A cloud session gets no machine verdict, and a hand check is weaker. Feeding MCP
  evidence into the gate is deferred to the owner, who decides if the cost justifies it.
- Exit 3 has two meanings. The gate's callers are the `pr-review` and `pr-autofix`
  skills and the `pr-review` prompt, whose text says not to retry it. The
  `repository-completion-proof` skill requires `all_passed: true`, which fails safe.
  No Python or workflow caller reads the gate's exit code.
- In a refused session a broken verifier reads `unknown`. Verifier exit 2 also means
  "PR not found" or "lib missing". It still never passes, and the hand check runs.
- The refusal is session-wide, not per row. Decision 8 is what keeps that safe.

### Residual risk

- The proxy can reword its body. Rows then read `failed`, as they did before this
  record. A test pins the patterns to bodies captured from a live session.
- `gh` comes from PATH. A launcher can put a project `.venv/bin` first, so a PR could
  ship a fake `gh`. Verifiers already trust the same binary, so the probe adds no new
  capability. On Windows a bare lookup can also search the cwd, as `_run_git` does.
- This has not run in a real refused session. A fake `gh` replayed captured bodies.

## Reversibility

Revert the commit to restore two-state rows. No code parses `verdict` or
`unknown_criteria`, so only the skill text moves with it. Revisit if a hand check misses
a real failure, or if the org connects the Claude GitHub App.

## References

- Issue #5232, `.project-toolkit/specs/SPEC-5232-gh-refused-session.md`
- ADR-035, ADR-059, ADR-099, ADR-100
- `src/claude/skills/github/references/transport-routing.md`
- `.project-toolkit/critique/ADR-120-debate-log.md`
- `.project-toolkit/critique/ADR-120-debate-log-2.md`
