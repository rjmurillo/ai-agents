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

### /review pass (2026-10-07)

The repository `/review` ran Stage 1 plus eight risk-selected axes and the correctness pass on tip `7084dfe36`. Stage 1 and all eight axes returned PASS. The correctness pass returned WARN.

| # | Axis | Finding | Resolution |
|---|------|---------|------------|
| 13 | correctness, qa | The negative drift test rebuilt the rule inline and tested its own copy. | Fixed. Both tests now call one helper, and fake workflows drive the negative cases. |
| 14 | analyst | Decision 5 said four workflows, the deferred table said four entries, and the Decision 2 table had no `claude.yml` row. | Fixed. |
| 15 | devops | The doubled smoke legs double runner minutes. | Fixed. Stated under Negative consequences. |
| 16 | reliability | The next scheduled run also cancels legs that wait for approval. | Fixed. Stated under Negative consequences. |
| 17 | correctness | The drift check missed the bracket form `secrets['NAME']`. | Fixed. The check matches both forms, and a test pins it. |

### Full panel completion (2026-10-07)

A Devin review on PR #6197 pointed out that round 3 ran two seats where AGENTS.md requires six. The owner chose to run the four missing seats. They reviewed head `13d02d1b0`.

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 18 | security | P1 | Self-review is allowed and the owner is the only reviewer. A process holding the owner's token can approve its own pending deployment through the REST API. | Recorded as Decision 11 item 7. A settings deny rule only slows this, so it is an owner decision, not a fix in this change. |
| 19 | security | P2 | The `claude.yml` approval controls spend, not prompt injection. | Fixed. Decision 3 says so and tells the reviewer to read the triggering event. |
| 20 | security | P2 | The Dependabot secret store was not checked. | Fixed. It holds 0 secrets, recorded in Decision 11 item 4. |
| 21 | security | P2 | Repository-level `FACTORY_API_KEY` shadows the `agent-droid` copy. | Recorded in Decision 11 item 4. The owner deletes it. |
| 22 | analyst | P2 | ADR-114 cited ADR-101:261. The sentence is at :269. | Fixed. |
| 23 | analyst | P2 | The `always()` line reference was stale. | Fixed. It is line 87. |
| 24 | analyst | P2 | `copilot-context-synthesis.yml` reads no provider secret, so its gate rests on the stanza alone. | Fixed. Decision 10 and the Positive consequence name it. |
| 25 | analyst | P2 | `docs/COST-GOVERNANCE.md` said agent checks never block. | Fixed. It now matches Decisions 5 and 7. |
| 26 | independent-thinker | P2 | `claude.yml` approval volume is larger than `@claude` replies, and waiting runs pile up with no concurrency group. | Recorded under Negative consequences, with run counts from the Actions API and a trigger. |
| 27 | independent-thinker | P2 | One review can approve several environments. | Fixed. Cited the REST API. |
| 28 | independent-thinker | P2 | Decision 12 shipped "not re-verified in this session". | Fixed. Quoted GitHub's documentation, read 2026-10-07. |
| 29 | independent-thinker | P2 | `agent-approval` is unused configuration. | Recorded as Decision 11 item 6. The owner decides. |

The high-level-advisor ruled every finding above as a fix or a record in this change. It ruled that the settings deny rule stays an owner decision.

### Votes (full panel)

| Seat | Vote |
|------|------|
| architect | Disagree-and-Commit |
| critic | Disagree-and-Commit |
| security | Disagree-and-Commit |
| analyst | Accept |
| independent-thinker | Disagree-and-Commit. The round 2 Block is lifted: the seat read the live API and found keys scoped and reviewers set. |
| high-level-advisor | Disagree-and-Commit |

All six seats Accept or Disagree-and-Commit. No seat blocks. The four late seats voted on head `13d02d1b0`. Their fixes landed in the next commit, and no seat re-voted on it.

## Round 4 (2026-10-08: deployment-approval deny rule and claude.yml concurrency)

Scope: a Claude Code deny rule against approving a pending deployment through `gh api`, and a job-level concurrency group on `claude-response`. ADR-114 Decision 11 item 7 and a Negative consequence changed. ADR-112 section 3 and a new gap G11 changed.

### Owner decisions

| ID | Decision |
|----|----------|
| D17 | Deny `gh api` calls to `pending_deployments` for Claude Code now. Record that Codex and Copilot CLI cannot express the rule. Defer a cross-harness hook to its own ADR-085 review. |
| D18 | Put the concurrency group on the `claude-response` job with `cancel-in-progress: false`. |
| D19 | Key comments and reviews on their own id, and share one key per thread only for push, label, assign, and issue events. |

### Panel

Full panel. The change adds an enforcement rule, so all six seats ran.

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 30 | architect | P1 | ADR-112 owns the deny set and gap table, and neither listed the rule. | Fixed. ADR-112 section 3 lists it, and gap G11 records its misses. |
| 31 | architect, critic | P1 | A replaced pending job is cancelled with no reply. | Fixed. Stated as a cost with a trigger. |
| 32 | critic | P1 | Whether a job waiting for a reviewer holds the running slot is unverified. | Fixed. ADR-114 states it is not documented and not observed. |
| 33 | architect | P2 | A dispatch never coalesces. | Fixed. Stated. |
| 34 | architect | P2 | ADR-026 defaults to `cancel-in-progress: true`. | Fixed. ADR-114 records the exception and says ADR-026 is not amended. |
| 35 | critic | P2 | The skipped-job claim was untested. | Fixed. Marked INFERRED in ADR-114 and the test docstring. |
| 36 | analyst | P1 | ADR-112 said the rule "stops" self-approval, which G11 contradicts. | Fixed. It says "slows". |
| 37 | analyst | P1 | The Codex `prefix_rule` claim had no source. | Fixed. Cited developers.openai.com/codex/rules, read 2026-10-08. |
| 38 | analyst | P2 | The `approveDeployments` mutation was unverified. | Fixed. Confirmed by schema introspection on 2026-10-08. |
| 39 | security | P2 | Bots, collaborators, and pushes can displace a pending request. | Fixed by D19 for comments and reviews. The thread-key exposure is stated. |
| 40 | security | P2 | The plain GET of the endpoint had no probe. | Fixed. A probe pins it. |
| 41 | security | P2 | G11 listed only two misses. | Fixed. G11 is marked illustrative and names more spellings. |
| 42 | independent-thinker | P1 | One key per thread drops human requests to save clicks on machine events. | Fixed by D19, which the owner chose after this finding. |
| 43 | independent-thinker | P1 | Label and assign events also share the thread key. | Fixed. Stated. |
| 44 | independent-thinker | P2 | The job-token approval claim was INFERRED. | Fixed. ADR-114 states it is unknown. |
| 45 | high-level-advisor | P2 | A test name overstated what it proves. | Fixed. Renamed. |

### Votes

| Seat | Vote |
|------|------|
| architect | Disagree-and-Commit |
| critic | Disagree-and-Commit |
| security | Disagree-and-Commit |
| analyst | Accept with changes; all changes applied |
| independent-thinker | Disagree-and-Commit |
| high-level-advisor | Accept |

No seat blocks. The seats voted before D19 changed the key from one per thread to the split key. The split key answers finding 42, and no seat re-voted on it.

### Owner action after the panel (2026-10-08)

The owner deleted `agent-approval`. A run still waiting on it made GitHub recreate it unprotected, so it took a second delete. ADR-114 Decision 11 item 6 and Decision 12 now record this. The change is a factual state update with no new decision, so no seat re-voted.
- 2026-10-08: COST-GOVERNANCE and a test comment now say `agent-approval` is deleted; the ADR states the recreation time from the deployment record. Factual updates, no re-vote.

## Round 5 (2026-10-08: Copilot leaves ai-review, plugin CLI smoke gates pull requests)

Scope: issue #6069 and REQ-047. Decision 2 table rows, Decision 5 (the unlisted blocking workflow), new Decision 13, Decision 11 items 8 and 9, a Negative consequence, Impact, and References. ADR-071 nightly references now name `plugin-cli-smoke.yml`.

### Owner decisions

| ID | Decision |
|----|----------|
| D20 | Move the `ai-review` callers `ai-metrics-analysis.yml`, `artifact-insight-scanner.yml`, and `pr-maintenance.yml` from Copilot to Claude in `agent-claude`. Copilot tokens for model review are not funded. |
| D21 | Keep a Copilot CLI smoke: the owner needs proof that skills and plugins load in Copilot. Every job that spends model tokens stays behind an approval environment. |
| D22 | The real-CLI smoke gates pull requests, because nobody reads the nightly. It is path-filtered on plugin-shipped paths, and the result passes when none changed. |
| D23 | Run the full Claude and Copilot matrix on Ubuntu, macOS, and Windows, and delete the nightly workflow. |
| D24 | Add a Codex leg now, with the same gates as Claude and Copilot. Shift checks left wherever possible. |
| D25 | The Copilot leg's gate is zero-token (`skill list`). Copilot prompt checks run when quota exists, and a classified quota skip is reported, not failed. |
| D26 | Budgets run out. Keys may go unfunded, and that gap is accepted for every provider. Zero-token load checks stay strict. Prompt checks that hit an exhausted quota or credit balance skip with a marker. Auth failures still fail. The moved `ai-review` jobs may fail on an unfunded key, which never blocks a merge. |

### Panel

Full panel. Decision 13 adds a blocking gate, so all six seats ran in parallel, each read-only on head `b663e0dd2`.

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 46 | critic, security | P0 | The quota marker also covered auth, transport, and rate-limit blocks, so a dead Copilot token passed. | Fixed. Only exhausted quota or credit carries the marker. Auth, transport, and Copilot rate limits fail. A Claude 429 counts as quota, because the CLI reports both limits the same way. Negative tests pin it (D26). |
| 47 | architect | P0 | ADR-094 Decision 2 named `action.yml` and the nightly as pin owners, and both became false. | Fixed. ADR-094 has a 2026-10-08 amendment. |
| 48 | critic, security | P1 | The trusted-context gate and the result reporter ran from the pull request tree, so a fork could rewrite them. | Fixed. Both, plus the skip gate, run from the base commit with `python3 -I`. |
| 49 | critic | P1 | Decision 13.1 claimed a pull request cannot change its own gate, but the workflow YAML comes from the head. | Fixed. The claim is narrowed, and review of the workflow diff is the stated control. |
| 50 | critic | P1 | The path list missed the gate's own scripts, `.github/plugin/marketplace.json`, `pyproject.toml`, and `uv.lock`. | Fixed. They are added, and a test checks that every script the workflow runs is listed. |
| 51 | architect | P1 | ADR-083 still named the nightly as the home of the base-alone e2e. | Fixed. ADR-083 has a 2026-10-08 amendment. |
| 52 | architect, critic, independent-thinker | P1 | ADR-071 said Renovate cannot auto-merge the CLI pins. `renovate.json` auto-merges all three, so a bump can merge before its smoke is approved. | Fixed in text. The in-place rewrite became a dated ADR-071 amendment that states the fact. The residual is tied to Decision 11 item 8. |
| 53 | architect, analyst, high-level-advisor | P1 | Decision 5 said "other six". The count is five. | Fixed. |
| 54 | analyst | P1 | Decision 13.5 said a waiting result blocks. By default, only a failed one does. | Fixed. Waiting blocks only with `--include-non-required`. |
| 55 | architect | P1 | The title and a Positive consequence still said agent checks never block. | Fixed. The title names the exception, and the consequence is scoped. |
| 56 | architect | P1 | The rollback had no step for Decision 13. | Fixed. A rollback row removes the ruleset check first. |
| 57 | high-level-advisor | P1 | Item 8 had no ordering. Requiring the check before it runs on `main` stalls every pull request. | Fixed. Item 8 requires one report on `main` first. |
| 58 | high-level-advisor | P1 | The move to `ANTHROPIC_API_KEY` landed on a key that had run out of credit on 2026-10-07. | Owner decision D26: an unfunded key is an accepted gap for advisory jobs. Item 9 records it with run 37583525191. |
| 59 | high-level-advisor, independent-thinker, critic | P1 | Each push needs a fresh approval click, and the ADR did not state that cost or the approval timeout and re-run behavior. | Fixed. Decision 13 items 3 and 6 state them, with a revisit trigger. |
| 60 | analyst | P2 | A `dispositions.json` entry can exempt a failed result. | Stated in Decision 13.5. |
| 61 | independent-thinker, critic, high-level-advisor | P2 | Codex runs fewer checks than D24's "same gates". | Stated in Decision 13.2: plugin and skill load only, and why. |
| 62 | independent-thinker | P2 | A model-judgment check could cite the exception as precedent. | Fixed. Decision 13 calls it deterministic load evidence. |
| 63 | security | P2 | Checkouts kept credentials in `.git/config`. | Fixed. Every checkout sets `persist-credentials: false`. |
| 64 | security, critic | P2 | The marker matched as a substring, and an all-skip run could pass with zero passing tests. | Fixed. Prefix match, plus a required pass for each leg's zero-token test. |
| 65 | security | P2 | Egress is audit-only, and the token is present while pull request code runs after approval. | Deferred. It is the Decision 10 residual. Trigger: an egress allowlist is proven on one Linux leg. |
| 66 | independent-thinker | P2 | Claude legs depend on subscription rate limits and token expiry. | A Claude 429 is marker-skipped as quota, and an expired token fails (Decision 13.4). Token ownership is the owner's. |
| 67 | analyst | P2 | Workflow and test comments cited "D6". | Fixed. They cite D25. |
| 68 | architect | P2 | `ai-review` outputs keep `copilot-exit-code` and `copilot-stderr` names fed by the Claude step. | Out of scope. A rename breaks callers. Flagged in the pull request body. |
| 69 | architect | P2 | Frontmatter date and Related Decisions were stale. | Fixed. |
| 70 | architect (round 2) | P2 | Item 8 said "reported once on `main`", but the workflow never runs on `main` by itself. | Fixed. Item 8 names a manual dispatch on `main` and notes that older pull requests get no result until their next push. |
| 71 | architect (round 2) | P2 | Decision 13.6 said agents cannot approve deployments, which item 7 contradicts. | Fixed. It says the deny rule only slows self-approval. |
| 72 | critic (round 2) | P1 | The trusted steps run `main`'s copy of the gate scripts, which this pull request adds or extends, so its own smoke fails. Later flag changes hit the same break. | Fixed in text. Decision 13.1 names the landing cost, the `workflow_dispatch` proof path, the owner-approved first landing, and the two-step rule for later flag changes. |
| 73 | critic (round 2) | P2 | A docstring said the marker "contains" while the code matches a prefix. | Fixed. |

### Votes

| Seat | Round 1 | Round 2 |
|------|---------|---------|
| architect | Block | Accept |
| critic | Block | Disagree-and-Commit; the landing cost is now stated |
| security | Block | Accept |
| analyst | Disagree-and-Commit | not re-run; its two P1 text errors are fixed (53, 54) |
| independent-thinker | Disagree-and-Commit | not re-run; its P1 is answered in text (52) and depends on Decision 11 item 8 |
| high-level-advisor | Disagree-and-Commit | not re-run; its four P1 items are fixed or answered by D26 (53, 57, 58, 59) |

All six seats Accept or Disagree-and-Commit. No seat blocks. Findings 72 and 73 landed after the critic's round 2 vote, and no seat re-voted on them.
- 2026-10-08: After the votes, commit `5b339a526` split the reporter into `smoke_result.py` and the quota reporting into `smoke_quota_report.py`, restored `scripts/ci/require_job_results.py` to `main`, and slimmed `assert_smoke_ran.py`. The `/review` security axis re-checked findings 48 and 64 at that commit: both scripts run from the base commit under `python -I`, and the marker is still a prefix match with a required pass. Factual update, no seat re-voted. Later `/review` fixes (`--no-renames` in the path filter, a parity test between the gate and the quota report) are recorded in the pull request.
- 2026-10-08: The `/review` reliability axis found that a manual cancel of the latest run leaves `CLI Smoke Result` skipped, which a required check reads as passing. Decision 13.3 records it as the Decision 10 residual, because the `!cancelled()` aggregator convention is kept and cancelling needs write access.
- 2026-10-08: Correction to finding 72's resolution. A branch `workflow_dispatch` cannot prove the legs, because the trust gate trusts a dispatch only on `refs/heads/main` (run 37846561785: `smoke trusted-context gate: untrusted`, legs skipped). Decision 13.1 now names the local smoke as the proof before merge and a dispatch on `main` as the first CI proof.
