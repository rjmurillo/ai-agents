# ADR Debate Log: ADR-114 Agent Workflows Run Only After Approval and Never Block Merges

## Summary

- **Status after review**: proposed. The owner decides acceptance.
- **Rounds**: 2. Round 1 reviewed the policy as an ADR-057 amendment. Round 2 reviewed ADR-114 after the owner moved the policy into its own ADR.
- **Outcome**: all six seats Accept or Disagree-and-Commit after the round 2 fixes, except independent-thinker, which voted Block on an owner-only action. See Votes.
- **Method note**: each seat was a fresh agent. Agents ran two at a time. Later seats saw a summary of earlier findings so they would not repeat them.

## Owner decisions

| ID | Decision |
|----|----------|
| D4, D6 | Agent workflows must not start on their own. They are non-blocking and run only after GitHub environment approval. `claude.yml` is excluded. |
| D8 | Include `slash-command-quality.yml` and amend ADR-057 in the same change. |
| D9 | Move the policy into its own ADR. ADR-057 keeps a pointer. |
| D10 | Identify agent checks by workflow file path read from the trusted ref, not by check name. |
| D11 | Merge with the repo-level secrets gap stated in the ADR. Secret moves are owner actions. |
| D12 | Gate `copilot-context-synthesis.yml`. Give `claude.yml` its own unprotected `agent-claude` environment to hold its token. |

## Round 1 (policy as an ADR-057 amendment)

| Seat | Key findings | Vote |
|------|--------------|------|
| security | P1: bare-name exemption is spoofable. P1: environment protection is not enforced in the repo. | Disagree-and-Commit |
| analyst | P1: `process-prs` name does not match its check. P1: two docs still say the spec check blocks. P1: two ADR-057 lines still read as blocking. | Disagree-and-Commit |
| architect | P1: a policy for nine workflows does not belong in an eval ADR. P1: the list is a second exemption registry with no reason or owner. | Disagree-and-Commit |
| critic | P1: no commit-status test. P1: matrix names untested. P1: a missing trusted ref fails closed with no log line. | Disagree-and-Commit |
| independent-thinker | P1: about 8 of 11 names never appear on a pull request. P1: key the exemption on the workflow path, not the name. | Disagree-and-Commit |
| high-level-advisor | Adopt path keys. Fix docs and tests. New ADR is the owner's call. | Disagree-and-Commit |

### Author response

The owner chose a new ADR (D9) and the path-keyed design (D10). ADR-114 was written. The list now holds four workflow paths, each with a reason and an owner. Commit-status rows and required checks stay blocking. A missing trusted ref prints a warning and exempts nothing.

## Round 2 (ADR-114)

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 1 | architect | P1 | The gate is not a trust boundary. ADR-101:261 says a pull request can delete the environment line. | Fixed. ADR-114 states it and records the owner override for spend control. |
| 2 | architect | P2 | Stale ADR-101 line references, no `review-by`, long Context, no detector for a non-agent job added to a listed file. | Fixed, except the detector. That gap is accepted in the ADR. |
| 3 | security | P2 | Exemption is per workflow file, not per job. | Accepted. Split into `agent-*.yml` deferred until a tenth pull-request agent workflow lands. |
| 4 | security | P2 | The reader script runs from the pull request tree. | Fixed for the gate path. The completion gate already byte-compares the script against the trusted ref. A direct run outside the gate is a recorded residual. |
| 5 | security | P2 | Require environment evidence before merge. | Fixed. The PR body lists it as an owner action. |
| 6 | critic | P1 | No pagination test. | Fixed. A test drives a listed row on page 1 and an unlisted same-name row on page 2. |
| 7 | critic | P1 | `why_pr_blocked.py` could disagree with the readiness script. | Fixed by test. It reports required checks only, so the two agree. Two tests pin it. |
| 8 | critic | P1 | Matrix rows untested. | Fixed. |
| 9 | critic | P2 | Edge rows and a needless list load when CI is ignored. | Fixed. |
| 10 | critic | P2 | No owner for prompt regressions missed before merge. | Deferred. Review is human only until the first regression found after merge. |
| 11 | analyst | P2 | Partial docs, three files calling the spec check required, unsourced claims about GitHub behavior. | Fixed. The environment auto-create claim is marked not re-verified. |
| 12 | independent-thinker | P0 | Model secrets are not scoped to the environment, so a job without the environment line can still spend. | Owner action (D11). The ADR states the gap and does not claim spend is stopped. Secret scope for three of the four secrets is unverified, not confirmed repo-level. |
| 13 | independent-thinker | P1 | Environment protection is unverified. An unprotected environment both runs unapproved and never blocks. | Owner action. The ADR names the silent failure. |
| 14 | independent-thinker | P1 | `copilot-context-synthesis.yml` was missing. | Fixed (D12). Ten workflows are gated. |
| 15 | high-level-advisor | none | Dispositions for findings 1 to 14. | Applied as listed. |

## Votes

| Seat | Vote |
|------|------|
| architect | Disagree-and-Commit |
| critic | Disagree-and-Commit |
| independent-thinker | Block |
| security | Disagree-and-Commit |
| analyst | Disagree-and-Commit |
| high-level-advisor | Disagree-and-Commit |

The Block rests on finding 12 and finding 13. Both need repository settings that only the owner can change. The high-level-advisor ruled that neither is a defect in the change, and the owner chose to merge with the gap stated (D11). The Block stands until the owner moves the secrets and records environment evidence. Votes were cast on head `e74810a09`. The fixes above landed in `b6e900e4a`. No seat re-voted on that head.

## Strategic checklist

- Chesterton's Fence: PASS. The ADR records why the workflows ran on their own and why that changes.
- Path Dependence: PASS. Rollback is a revert of the workflow lines and the list.
- Core vs Context: N/A.
- Second-System: PASS. The split into dedicated files is deferred with a trigger.

## Round 3 (2026-10-07: per-provider environments)

Scope: the owner replaced the single `agent-approval` environment with one environment per provider and gated `claude.yml`. Decisions 1, 2, 3, 5, 11, and 12 changed, and the smoke job split by CLI.

### Owner decisions

| ID | Decision |
|----|----------|
| D13 | Create `agent-claude`, `agent-codex`, `agent-copilot`, and `agent-droid`, each with required reviewer `rjmurillo`. "Prevent self-review" is off because the owner is the only reviewer. |
| D14 | Gate `claude.yml` through `agent-claude`. This reverses D4's `claude.yml` exclusion. |
| D15 | Scope each vendor key to its environment under the vendor's documented name, and delete the repository-level `ANTHROPIC_API_KEY`. |
| D16 | Split the nightly smoke by CLI so each leg reads one provider's key. |

### Panel

Reduced panel of architect and critic, with the critic also covering security. The change touches workflow gates, so AGENTS.md calls for the full panel. The owner's session cap allows three subagents in total, and one built the change. This round therefore ran two seats. The owner decides whether a full panel is needed before acceptance.

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 1 | architect, critic | P1 | ADR-057 lines 92 and 267 still named `agent-approval`. | Fixed. Both name `agent-claude`. |
| 2 | architect | P1 | Counts disagreed: "Ten workflows", "other six", and "eleven" in the docs. | Fixed. Decision 2 names eleven, and Decision 5 lists `claude.yml`. |
| 3 | architect | P1 | `claude.yml` triggers on `pull_request` and now waits for approval, but it was not listed. A rejected approval would block a merge. | Fixed. `claude.yml` joins `advisory_agent_workflows`, and a test pins it. |
| 4 | architect | P1 | Decision 12 still called the `claude.yml` triggers a spend actor that runs by design. | Fixed. The clause is removed. |
| 5 | critic | P1 | Four moved jobs read `BOT_PAT`, which exists nowhere. | Stated in Decision 11 item 5. The gap predates this change. |
| 6 | architect, critic | P2 | The rollback row said the jobs return to `bot-secrets`. That environment has no secrets now. | Fixed. Rollback must re-create the repository-level secrets. |
| 7 | critic | P2 | "Each leg needs its own approval" is likely wrong. Approval is per environment. | Fixed. A smoke run waits on two environments. |
| 8 | architect | P2 | A dispatch cancels smoke legs that are waiting for approval. | Fixed. Stated under Negative consequences. |
| 9 | critic | P2 | Decision 12 listed environments without their contents. | Fixed. Reviewers and secret counts, read from the Environments API on 2026-10-07. |
| 10 | critic | P2 | The `assert_smoke_ran.py` docstring described the old two-CLI count. | Fixed. |
| 11 | critic | P2 | The first `uv run` in a smoke step syncs the project with a key in scope (CWE-829). | Deferred. It predates this change. It is flagged in the pull request body. |
| 12 | architect | P2 | Frontmatter `date` is not updated. | Kept. `date` records creation. The index row is regenerated. |

### Votes

| Seat | Vote |
|------|------|
| architect | Disagree-and-Commit |
| critic | Disagree-and-Commit |

Both seats voted before the fixes above. Both conditioned their votes on the P1 fixes, and all four P1 findings are fixed. No seat re-voted on the fixed head.
