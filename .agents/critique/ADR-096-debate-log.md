# ADR-096 debate log

Subject:
`.agents/architecture/ADR-096-trusted-vendor-provenance-gate.md`

Skill: `.claude/skills/adr-review/SKILL.md`, six-agent debate, four rounds plus
one post-acceptance amendment review.

## Outcome

ADR-096 is accepted. All six roles voted ACCEPT in the final round.
`implemented` remains false until PR #4846 merges.

| Role | Final vote |
|---|---|
| architect | ACCEPT |
| critic | ACCEPT |
| independent-thinker | ACCEPT |
| security | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |

## Debate progression

### Round 1

The first review supported the trusted-base design but found missing decision
records and failure boundaries:

1. Explain why ADR-066's local hook valve does not apply to a hosted required
   status check, and document repository administration as break glass.
2. Make `merge_group` trust updates fail closed until originating pull request
   identity can be resolved.
3. Narrow the dual-channel claim to channel-specific failures.
4. Define rollback owner, order, and target time.
5. Record bootstrap smoke evidence before enabling the required context.
6. Tie security claims to named tests.

The ADR and implementation were revised. `merge_group` trust updates now fail
closed. Head-gate startup preserves a created Check Run ID when Commit Status
publication fails.

### Round 2

Reviewers checked the revised trust model, immutable materialization, dual head
gates, pin update authorization, rollback, and test evidence. Remaining
findings concerned governance evidence, retry classification, rollback
detection, and citations for candidate configuration rejection.

### Round 3

Five roles voted ACCEPT or Disagree-and-Commit. The critic blocked acceptance
because the ADR exceeded ADR-006's 100-line workflow target without the
Chesterton's Fence analysis required by
`.agents/governance/ADR-EXCEPTION-CRITERIA.md`.

The following changes resolved that block and the remaining P1 findings:

1. Added the verbatim ADR-006 rationale.
2. Documented two attempted alternatives.
3. Bounded the exception to
   `.github/workflows/vendor-provenance.yml`.
4. Quantified the 184 total and 128 non-comment workflow lines.
5. Recorded testing impact, precedent risk, reversibility, and a review
   trigger.
6. Made authentication, forbidden, not-logged-in, and unauthorized GitHub API
   failures stop after one attempt.
7. Added tests for one-attempt authentication failures.
8. Defined repository-wide blockage detection, alert path, and the start of
   the 30-minute mitigation target.
9. Added named confirmation tests for unpinned executables, `.npmrc`,
   `uv.toml`, and markdownlint configuration.

### Round 4

All six roles reviewed the revised ADR and implementation. Each voted ACCEPT.

One reviewer initially returned BLOCK after a project-scoped semantic tool
resolved relative paths against the wrong checkout. Direct reads of the
requested absolute worktree showed that `_start_head_gates`,
`_finish_head_gates`, and their CLI flags were present. The reviewer retracted
the finding and voted ACCEPT. The critic also rechecked the same paths and
confirmed the correction.

### Post-acceptance amendment review

Later review findings changed ADR-096's trust-boundary wording and gitlink
policy record. All six roles reviewed the amended ADR and implementation.

The architect initially voted BLOCK because gitlink rejection had been moved
behind relevance filtering. The workflow was restored to reject every gitlink
before relevance. ADR-096 now records a repository-wide submodule ban because
a gitlink delegates code identity to an external repository outside the
authenticated tree.

The high-level advisor initially voted BLOCK after a sampled read skipped
`tests/ci/test_validate_vendor_provenance.py:850-857`. A direct absolute-path
read confirmed that `test_workflow_rejects_gitlinks_before_relevance` asserts
both required invariants: gitlink rejection precedes relevance, and the
gitlink step has no `if:` key. The advisor retracted the finding.

The amended ADR also limits SHA-256 trust claims to repository-owned artifacts
and names hosted runner tools as platform trust roots.

| Role | Amendment vote |
|---|---|
| architect | ACCEPT |
| critic | ACCEPT |
| independent-thinker | ACCEPT |
| security | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |

### Merge queue trust amendment

A later security review found that `merge_group` executes workflow YAML from
the synthetic queue head. Candidate changes could therefore replace the
privileged workflow and retain its required name and write permissions.

The workflow removed its `merge_group` trigger. ADR-096 now states that merge
queue support needs a separate base-owned execution design. It also records
that this user-owned repository is currently ineligible for merge queues.

The architect initially voted BLOCK because two stale tests still required
`merge_group`, and no test pinned the workflow exception measurement. Those
tests were removed. Static coverage now asserts that `merge_group` is absent
and that the workflow remains 181 total and 125 non-comment lines.

The analyst twice resolved project-scoped tools against the wrong checkout.
Final deterministic evidence used the exact worktree path: ADR-096 existed,
Decision item 10 matched the workflow, direct measurement returned 181 and
125, and the provenance suite passed 231 tests.

| Role | Merge queue amendment vote |
|---|---|
| architect | ACCEPT |
| critic | ACCEPT |
| independent-thinker | ACCEPT |
| security | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |

### Immutable maintainer identity amendment

A later review found that mutable GitHub login names can be renamed and later
reacquired. Trust-anchor authorization now uses numeric GitHub user IDs from
`pull_request.user.id` and `sender.id`. Both IDs must match the immutable
allowlist, and only `opened` or `synchronize` can authorize updates.

Five roles voted ACCEPT. The independent-thinker voted Disagree-and-Commit,
recording single-maintainer succession, collaborative `edited` event failures,
automated dependency pin churn, and signed-commit alternatives as follow-up
risks. Security found no unresolved P0 or P1 issue in the numeric-ID flow.

| Role | Numeric identity amendment vote |
|---|---|
| architect | ACCEPT |
| critic | ACCEPT |
| independent-thinker | DISAGREE-AND-COMMIT |
| security | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |

## Verification

From `/home/richard/sessions/pr-autofix-4846`:

```text
uv run pytest -q tests/ci/test_validate_vendor_provenance.py
224 passed in 11.12s
```

Direct file checks confirmed:

- `_start_head_gates` and `_finish_head_gates` exist in
  `scripts/ci/validate_vendor_provenance.py`.
- The validator CLI defines every flag used by
  `.github/workflows/vendor-provenance.yml`.
- Authentication failures use one GitHub API attempt.
- The ADR-006 quote matches the source ADR.
- The exception record satisfies every required analysis category.

## Dissent

No final dissent. Earlier concerns were resolved in the ADR, implementation,
or test evidence.

## Strategic assessment

- Chesterton's Fence: PASS
- Path dependence and reversibility: PASS
- Core versus context: PASS, repository trust enforcement is local policy
- Second-system effect: PASS, scope is one workflow and one validator
- Overall: APPROVED
