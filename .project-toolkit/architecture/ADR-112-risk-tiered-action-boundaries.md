---
id: ADR-112
status: proposed
date: 2026-09-28
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
review-by: 2027-03-28
---

# ADR-112: Risk-Tiered Action Boundaries for Agent Tools

## Status

Proposed (2026-09-28, issue #5767, child of epic #5456). Implemented in the
same change. Requirement: REQ-043. Tasks: TASK-052.

## Date

2026-09-28

## Context

`AGENTS.md` carried the autonomy guardrail as one prose line: act on
reversible internal work, confirm before irreversible external work. Its
Never list named force-push and `--no-verify`. Nothing at agent time enforced
either. The owner runs agents in `bypassPermissions` mode (an operator
setting, not repository configuration), where nothing prompts, so prose was
the only barrier between a mistaken or prompt-injected agent and an
irreversible action.

Measured at `8050657d6`:

- `.claude/settings.json` `permissions.deny` held 8 rules, all git
  config-injection flags for the security agent (issue #4781).
- 29 of 31 Claude agents carried no `tools:` key, so Claude Code granted them
  every tool, including Bash, Edit, Write, and every MCP mutator.
- `code-reviewer` promised read-only behavior, and its own text admitted the
  promise held on three harnesses, not Claude.
- `merge_pr.py` reported `merged` on a zero exit code without reading the PR
  back, and did not pin the head SHA it had checked.

Constraints that shape the answer:

- ADR-097 retired every tool-use hook. `.claude/rules/tool-use-hook-bar.md`
  MUST 2 requires a host-native declarative surface to be ruled out first.
- ADR-085 Decision 1: Copilot CLI has no committed permission surface.
- ADR-101: enforcement must sit above the actor it constrains.
- Claude Code evaluates deny, then ask, then allow. Deny holds in
  `bypassPermissions` mode. The docs list `bypassPermissions` as running
  "Everything" without asking, so an `ask` rule is not a reliable hold.

### Control inventory

Every existing control that bounds an agent action, with its plane and kind.
Enforced means a deterministic mechanism refuses the action. Advisory means
the model must choose to comply.

| Control | Plane | Kind | Tier |
|---|---|---|---|
| `permissions.deny`, git config injection (8 rules) | Claude harness | Enforced | Consequential |
| `permissions.deny`, consequential set (this ADR) | Claude harness | Enforced | Consequential |
| GitHub ruleset on `main`: `deletion`, `non_fast_forward`, `pull_request`, `required_status_checks`, `required_linear_history`, `copilot_code_review` | Server | Enforced | Shared repository |
| `git_hook_policy.py` pre-push force-push guard (`FORCE_PUSH_OK` escape) | Git hook | Enforced locally, bypassable by `--no-verify` | Shared repository |
| `audit-hook-bypass.yml` and `detect_hook_bypass.py` | CI | Detects after the fact | Shared repository |
| `safe_push_pr_branch.py`: explicit refspec, pinned lease, porcelain check, `ls-remote` readback, audit record | Script | Enforced when used | Shared repository |
| `merge_pr.py`: pinned head, readback, recovery, audit (this ADR) | Script | Enforced when used | Shared repository |
| `auto_merge_guard.py`, `run_completion_gate.py`, `check_pr_live_state.py` | Script | Enforced when used | Shared repository |
| Agent `tools:` lists on Claude (analyst, security, code-reviewer, comment-analyzer) | Claude harness | Enforced | Per agent |
| Copilot and VS Code `tools_copilot` and `tools_vscode` lists | Copilot harness | Enforced | Per agent |
| `AGENTS.md` Ask First, Never, and Autonomy Guardrail lines | Prompt | Advisory | All |
| Agent prompt limits (for example, security "no shell") | Prompt | Advisory unless backed by a grant | Per agent |
| `tests/hooks/test_zero_tool_use_hooks.py` | Test ratchet | Enforced at CI | Hook surface |
| Generated projections (`build_all.py --check`) | CI | Enforced | Generated artifacts |

## Decision

Sort every agent action into four tiers, deny the highest tier at the Claude
harness, check shared-repository mutations inside the script that performs
them, and record every gap this leaves open.

### 1. Four action tiers

| Tier | Examples | Minimum authority | Preconditions | Approval | Evidence | Post-action verification |
|---|---|---|---|---|---|---|
| Read-only | read, search, `git diff`, `gh pr view` | Read tools | None | None | None | None |
| Reversible local | edit files in a worktree, run tests, local commit | Edit, Bash | Worktree outside the clone; not on `main` | None | Diff and test output | Tests or `git status` |
| Shared repository | push a branch, open or merge a PR, comment, label, generated projections | Skill script or `git push` | Target verified by number and SHA; branch not stale | Server rules (review, checks) and the user's task request | Script envelope with audit record | Readback of the target state |
| Consequential | force push, hook bypass, recursive delete, repository delete or rename, visibility, secrets, credentials, admin merge, protection or collaborator changes | Human only | Not applicable | The human runs it in their own shell or through the `!` prefix | Human action | Human |

An action whose tier is unclear takes the higher tier.

### 2. Canonical owner

This ADR owns the tier contract and the gap table. Enforcement lives on the
surfaces below. A new guardrail maps to a tier here; it does not add a policy
file.

| Tier | Enforcement surface |
|---|---|
| Consequential | `permissions.deny` in `templates/hooks/settings.tmpl`, rendered to `.claude/settings.json`; pinned by `tests/test_action_tier_deny_rules.py` |
| Shared repository | `safe_push_pr_branch.py`, `merge_pr.py`, and the GitHub ruleset on `main` |
| Reversible local | Worktree and branch policy in `git_hook_policy.py`; advisory elsewhere |
| Read-only | Explicit `tools:` grants |

### 3. Deny, not ask, for the consequential tier

A consequential command is denied. There is no agent-side approval path:
approval means the human runs the command. `ask` rules are not used, because
`bypassPermissions` mode runs without prompting and an ask that never fires
is prose with extra steps.

The deny set covers: `git push` with `--force`, `-f`, bare
`--force-with-lease`, `+refspec`, or `--mirror`; `git commit` and `git push`
with `--no-verify` or `commit -n`; `rm` with recursive and force flags in
eight spellings; `gh repo delete|archive|rename|edit`, `gh release delete`,
`gh issue delete`, `gh label delete`, `gh secret`, `gh variable set|delete`,
`gh pr merge --admin`; `gh api` with a DELETE method, and
`gh api` against branch protection or collaborator endpoints.

A lease pinned to an observed SHA (`--force-with-lease=<ref>:<sha>`) stays
allowed. `pr-autofix` and `safe_push_pr_branch.py` depend on it, and the
server ruleset still refuses a non-fast-forward to `main`.

### 4. Shared-repository checks live in the script

Only a script sees both the intent and the result. `merge_pr.py` now:

- takes `--expected-head-sha` and refuses a PR whose head differs, with no
  merge call (wrong target, stale branch);
- passes `--match-head-commit` so GitHub refuses a head that moved after the
  check;
- reads the PR back after every attempt and reports `merged` only on
  `state: MERGED`, `auto-merge-enabled` only with an `autoMergeRequest`, and
  exit 3 otherwise;
- refuses when it has no head SHA to pin;
- treats a failed, refused, or timed-out command followed by a `MERGED`
  readback as a recovered success, and an armed auto-merge request as queued;
- reports success only when the readback head equals the pinned head;
- returns `action: none` for an already merged PR, so a retry never merges
  twice;
- emits an audit record on every result, refusals included: actor, target,
  action, approval, result, rollback, residual risk. The rollback field is a
  strategy-correct command for a human to run (`git revert -m 1` for a merge
  commit, `git revert` for a squash, per-commit for a rebase).

`--expected-head-sha` catches a wrong PR number only when the caller passes
the SHA it reviewed. `pr-autofix` passes its triage head. Without the flag,
the pin still stops a head that moves between the check and the merge.

`safe_push_pr_branch.py` already met this bar for pushes and is kept.

### 5. Grant map

Claude grants. Copilot class is the widest toolset in `tools_copilot`:
`executor` (shell and edit), `editor` (edit, no shell), or read.

| Agent | Tier by contract | Claude grant | Copilot class | Disposition |
|---|---|---|---|---|
| analyst | Read-only | Explicit read list | read | Keep |
| code-reviewer | Read-only | Explicit read list (this ADR) | read | Removed Bash, Edit, Write; callers pass the diff, and a standalone default-scope review returns BLOCKED on Claude |
| comment-analyzer | Read-only | Explicit read list (this ADR) | read | Removed Bash, Edit, Write |
| security | Read-only plus report writes | Explicit list, Write, no Bash | editor | Keep (issue #4781) |
| critic, independent-thinker, high-level-advisor, issue-feature-review, negotiation, roadmap | Read-only plus report writes | All tools | editor | Keep, gap G1 |
| pr-test-analyzer, silent-failure-hunter, type-design-analyzer | Read-only plus report writes | All tools | read | Keep, gap G1 |
| quality-auditor, dependency-auditor | Read-only plus report writes, runs tools | All tools | executor | Keep, gap G1 |
| architect, explainer, milestone-planner, task-decomposer, skillbook, retrospective, backlog-generator | Reversible local (documents) | All tools | editor | Keep, gap G1 |
| implementer, debug, code-simplifier, janitor, qa | Reversible local | All tools | executor or editor | Keep; needs Bash for tests |
| devops | Shared repository (workflows) | All tools | executor plus `github-cicd` | Keep; `run_workflow` is gap G5 |
| orchestrator, pr-comment-responder, merge-resolver | Shared repository | All tools | executor | Keep; pushes and PR replies are their job |

The disposition "Keep, gap G1" means no measured accepted-task data shows
whether the agent needs Bash or Edit. Removing either without that data could
break a live workflow. Every Claude agent with Bash is bounded by the
consequential deny set, which is session-wide.

### 6. Enforced versus advisory

| Claim | Status |
|---|---|
| An agent cannot force-push, bypass hooks, recursively delete, or change repository security settings through a denied command spelling | Enforced on Claude |
| The same on Copilot CLI | Advisory (no committed permission surface, ADR-085) |
| A merge through `merge_pr.py` is pinned, read back, and audited | Enforced when the script is used |
| An agent uses `merge_pr.py` rather than raw `gh pr merge` | Advisory (`AGENTS.md` "Raw `gh`" Never item) |
| `main` cannot be force-pushed, deleted, or merged without review | Enforced server-side |
| Read-only agents do not edit | Enforced for analyst, code-reviewer, comment-analyzer; advisory for the rest |
| "Ask first" for architecture, ADRs, breaking changes, security | Advisory |

### 7. Open enforcement gaps

This ADR does not claim full protection. Each gap below is either pinned as an
absence in `tests/test_action_tier_deny_rules.py::KNOWN_GAPS` or states why
nothing pins it.

- **G1. Broad Claude grants.** 27 agents inherit every tool. Claude Code has
  no per-agent permission rule surface; `tools` and `disallowedTools` add or
  remove whole tools. Scoping needs measured task data (#5456, #5400).
- **G2. Command-text matching.** Deny rules match text, so equivalent
  spellings pass: `git push origin :branch` (remote delete),
  `git commit -anm` (combined flags), `LEFTHOOK=0 git commit`,
  `git -c core.hooksPath=...`, `find -delete`, and a forced ref update through
  `gh api ... -X PATCH -F force=true`, and a lease pinned to a ref but not a
  SHA (`--force-with-lease=<ref>`). The server ruleset covers `main`; other
  branches rely on CI detection. `gh auth token` stays allowed because the
  pre-push recipe in `.agents/governance/GOTCHAS.md` provisions the Copilot
  token with it. The test matcher does not model `$(...)` nesting, which the
  harness does check, so a neighbor test cannot prove a nested command runs.
- **G3. Copilot CLI.** No deny surface. Copilot agents rely on their
  `tools_copilot` lists and prose. The `implementer` `github-code` toolset
  can push files through the API, which skips local git hooks.
- **G4. Plugin consumers.** `permissions.deny` lives in this repository's
  settings. It does not ship in the plugin, so a consumer install gets none of
  the consequential deny set.
- **G5. Workflow dispatch.** `devops` holds `run_workflow` on Copilot. No
  tier check gates which workflow it dispatches.
- **G6. Merge queues.** `merge_pr.py` reads `autoMergeRequest`, not a merge
  queue entry. This repository has no merge queue rule; a consumer repository
  with one would see a queued merge reported as exit 3, which fails safe.
- **G7. Raw commands.** An agent that calls `gh pr merge` directly skips the
  script checks. Only the "Raw `gh`" prose rule prevents it.
- **G8. MCP merge.** The GitHub MCP `merge_pull_request` tool has no pin,
  readback, or audit. The github skill's transport table now tells the agent
  to read the PR before and after, which is advisory.
- **G9. No automated rollback.** No script reverts a merge or a push. The
  audit record names the command a human runs, so there is no failed-rollback
  code path to test; the pinned lease in `safe_push_pr_branch.py` records the
  prior remote SHA as the recovery point.
- **G10. Auto-merge is not head-pinned.** `set_pr_auto_merge.py` arms
  GitHub auto-merge, which merges whatever head passes checks. A push after
  the request lands is merged without a new review of that head, unless the
  repository requires review on the new push.

## Rationale

### Alternatives Considered

| Alternative | Why not |
|---|---|
| PreToolUse hook classifying every Bash call | ADR-097 bar: hot-tool blast radius (#5013), Copilot matcher widening, and the retired dispatcher machinery |
| `permissions.ask` for the consequential tier | Does not hold in `bypassPermissions` mode |
| Deny all `git push` and `gh pr merge` | Blocks the `AGENTS.md` End gate and this repository's automation |
| A new rule file for the tier contract | Adds an always-loaded policy layer; the epic asks for subtraction |

### Trade-offs

Deny rules are cheap and certain for the spellings they name, and blind to
the rest. The ADR names the blind spots instead of widening the rules until
they deny legitimate work.

## Consequences

### Positive

- The highest-impact Never items become harness-enforced on Claude.
- A merge result is read from GitHub, not inferred from an exit code.
- Two agents whose contract says read-only are read-only on all harnesses.

### Negative

- A human must run denied commands. That is the intended approval path.
- A commit message passed with `-m` that contains `--no-verify` or ` -n `
  followed by a space is denied. Use `-F` or a heredoc.
- Raw `gh api -X DELETE` is denied even for label or reaction removal. Use
  the github skill scripts, which run through a subprocess the deny list does
  not see.

### Neutral

- `AGENTS.md` keeps one line for the guardrail; it now points here.

## Impact on Dependent Components

- `git-advanced-workflows` recipe pins its lease to an observed SHA.
- `pr-autofix` says "never `--no-verify`" instead of "avoid if possible".
- `tests/claude_permission_matcher.py` now holds the deny matcher model that
  `tests/test_security_agent_git_write_guard.py` and
  `tests/test_action_tier_deny_rules.py` share.

## Implementation Notes

Edit `templates/hooks/settings.tmpl`, then run
`uv run python build/scripts/build_all.py`. A new consequential rule needs an
exploit in `CONSEQUENTIAL` and a neighbor in `NEIGHBORS`, or
`test_every_consequential_rule_denies_a_probed_command` fails.

## Related Decisions

- ADR-085 (cross-harness permission surface asymmetry)
- ADR-097 (zero tool-use hooks)
- ADR-101 (enforcement planes)
- ADR-105 (terminal-state completion contract)

## References

- Issue #5767; epic #5456
- <https://code.claude.com/docs/en/permissions>
- <https://code.claude.com/docs/en/permission-modes>
