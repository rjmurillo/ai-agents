# ADR Debate Log: ADR-076 deprecated and ADR-090 rejected after the lease removal

Panel: reduced (architect and critic). The edits change status metadata, one frontmatter flag, and add a pointer to history. No executable enforcement changes, and no rule that another gate reads changes. The AGENTS.md trigger for the full panel does not apply.

## Summary

- **Rounds**: 1 review round, then one revision
- **Outcome**: Consensus after revision (architect Accept-With-Changes, critic Accept-With-Changes, all changes applied)
- **Final Status**: ADR-076 `deprecated`, ADR-090 `rejected`. Both keep `superseded-by: null`.

## Scope

Issue #5696. PR #5697 (commit 359fae2f0) removed the advisory branch-ownership lease from `pr-autofix`. It deleted `pr_autofix_lease.py`, its test module, and the lease steps in the skill body. Two records still described the lease as live:

- ADR-076 was `accepted` and said the Phase-1 tooling ships with its acceptance.
- ADR-090 was `proposed` and amended ADR-076.

The edit moves each record's old Status text under a `### History` subsection and opens the Status section with the new state. `check_adr_lifecycle.py` requires that opening. The README index moves with the status.

Reviewers got the diff and a short brief. They did not get the author's reasoning. Each ran as a separate `claude -p --model sonnet` session with read-only tools (Read, Grep, Glob) and the role prompt body from `.claude/agents/<role>.md`.

## Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Accept-With-Changes | Dispositions fit. SHA gate claim holds. Debate log cited wrong template lines. |
| critic | Accept-With-Changes | No successor ADR needed. Same wrong line numbers. `implemented: false` contradicts "shipped then abandoned". |

## Findings and dispositions

| Priority | Finding | Disposition |
|----------|---------|-------------|
| P1 | Debate log cited SHA gate lines 783, 659, 1061 in `pr-autofix.SKILL.md.tmpl`; those lines hold unrelated text | Fixed. The gate is at lines 128, 701, 887, and 1174. |
| P1 | "about 500 marker comments over 33 hours" had no traceable source | Source is issue #5160 (514 of 523 comments on PR #5078 were lease markers, 2026-08-18 to 2026-08-19) and the deleted module's `RENEW_SKIP_MARGIN` comment at 359fae2f0^. |
| P1 | Debate log claimed headless sessions with no evidence | Reworded above to name the command and tools. |
| P2 | ADR-076 kept `implemented: false` although the module shipped | Fixed. ADR-076 is `implemented: true`. ADR-090 stays `false` because nothing was built. |
| P2 | "every lease gate in the skill body" read as if the SHA gate went too | Fixed. The text now says "the lease steps in the skill body". |
| P2 | `ADR-104-gate-tier-placement-and-budgets.md:778` lists ADR-090 as an indirect impact tied to its lease TTL | Out of scope. Editing ADR-104 needs its own debate. Flagged in the PR body. |
| P2 | `check_pr_round_cap.py:7` says "The lease and live-state gate protect against racing", while lines 17 and 112 call the lease retired | Out of scope. The fix belongs in the generated source's origin. Flagged in the PR body. |
| P2 | Three `.serena/memories/pr-autofix/` notes and `tests/evals/skill-scenarios/pr-autofix.json` still name the lease | Out of scope. Memories are data, and the eval may be a deliberate negative case. Flagged in the PR body. |
| P2 | README lists ADR-076 under Retired with "not recorded" as successor | Accepted. `superseded-by: null` is correct, and the Status section says no successor exists. |

No P0 findings. No Block positions.

## Verified facts

- `git ls-files` shows no `pr_autofix_lease` module or test file on the branch.
- `templates/skills/pr-autofix.SKILL.md.tmpl` names the Force-Push Safety SHA gate as the concurrency boundary at lines 128, 701, 887, and 1174.
- The deleted module (359fae2f0^) never contained `holder_id`, so nothing was built from ADR-090.
- `check_adr_lifecycle.py` passes with 0 violations after the revision (output in the PR body).

## Recommendation

Accept both status changes. A new proposal for issue #3413 needs its own ADR with a store other than PR comments.
