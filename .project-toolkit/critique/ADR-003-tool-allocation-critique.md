---
date: 2026-03-25
subject: ADR-003 Role-Specific Tool Allocation
verdict: CONCERNS
reviewer: critic
---

# Plan Critique: ADR-003 Agent Tool Selection Criteria

## Verdict

**CONCERNS (P0: 2, P1: 3, P2: 4)**

The ADR is structurally sound and the rationale for role-specific allocation is well-documented. However, the document has drifted significantly from the actual agent files it governs. Tool counts are wrong in multiple rows, agent names are stale, and 8 agents in `.github/agents/` have no representation in any table. The PR #1517 changelog entry is insufficient documentation for a cross-cutting change.

## Issues Found

### P0: Must Fix (Breaks ADR Authority)

**P0-1: Tool count targets are violated across 5 agents with no acknowledgment**

The ADR states the chosen option provides "3-9 tools per agent" and the Confirmation section requires "3-9 entries." The actual agent files show:

| Agent | ADR Count | Actual Count | Tools Missing from ADR |
|-------|-----------|-------------|------------------------|
| orchestrator | 15 | 20 | `vscode`, `github/list_workflow_runs`, `github/get_workflow_run`, `github/list_pull_requests`, `github/issue_read` (5 unlisted) |
| devops | 13 | 18 | `github/list_workflows`, `github/get_job_logs`, `github/rerun_failed_jobs`, `github/list_releases`, `github/get_file_contents` (5 unlisted) |
| implementer | 13 | 16 | `github/create_or_update_file`, `github/update_pull_request`, `github/add_issue_comment` (3 unlisted) |
| analyst | 11 | 18 | `github/search_users`, `github/get_file_contents`, `github/list_commits` (3 unlisted) |
| explainer | 4 | 6 | `vscode`, `memory` (2 unlisted; `edit` listed but absent) |

The ADR's Complete Tool Allocations table is not a summary. It claims to be the reference. These are not minor rounding errors. Orchestrator's actual count (20) is 33% above the stated maximum (15), which is itself above the target ceiling (9). No rationale documents why these thresholds were exceeded.

**P0-2: 8 agents in `.github/agents/` are absent from all ADR tables**

The following agents exist as files but appear nowhere in the Core Operations table, Specialty Tools table, Complete Allocations table, or the "Agents without GitHub tools" exclusion list:

- `code-reviewer` (no tools frontmatter present in file)
- `code-simplifier` (no tools frontmatter present)
- `comment-analyzer` (no tools frontmatter present)
- `milestone-planner` (has tools: read, edit, search, cloudmcp-manager/*, serena/*)
- `pr-test-analyzer` (no tools frontmatter present)
- `silent-failure-hunter` (no tools frontmatter present)
- `task-decomposer` (has tools: read, edit, search, cloudmcp-manager/*, serena/*)
- `type-design-analyzer` (no tools frontmatter present)

This is not a minor omission. The ADR declares itself the governance document for tool allocation. Agents that exist outside its scope are ungoverned. For agents with no `tools:` frontmatter at all, it is unclear whether they inherit a default set (defeating the ADR's purpose) or have no tools (making them non-functional).

### P1: Should Fix (Reduces Reliability)

**P1-1: Agent names in ADR do not match file names**

The ADR references `planner` and `task-generator`. The actual files are `milestone-planner.agent.md` and `task-decomposer.agent.md`. The "Agents without GitHub tools" list and the Complete Allocations table both use the old names. A reviewer checking compliance cannot match ADR rows to files without guessing.

**P1-2: Inconsistencies across the three allocation tables**

The ADR has three tables that should describe the same agents: Core Operations, Specialty Tools, and Complete Allocations. They diverge:

- `backlog-generator` appears in Specialty Tools and Complete Allocations but NOT in Core Operations.
- `explainer` has `edit` marked as present in Core Operations. The actual agent file has `edit`. But the ADR's Complete Allocations row for `explainer` lists only `read, edit, cloudmcp-manager/*, serena/*` (count: 4), while the actual file adds `vscode` and `memory`, making the actual tool set different from all three tables.
- `security` is listed with `perplexity/*` in Complete Allocations but the Specialty Tools Research column entry says only "web, perplexity". The actual file confirms `perplexity/*` is present, but the Specialty Tools anti-pattern note ("Agents with research tools: analyst, independent-thinker, security") only mentions three agents while `backlog-generator` also has `web`.

**P1-3: PR #1517 changelog entry does not constitute decision documentation**

The changelog records what changed (GitHub search tools added to 6 agents) and references PR #1517 and Issue #1511. It does not record:

- Why each specific tool was added to each specific agent (the rationale differs between devops getting `search_repositories` vs implementer not getting it)
- Whether the 3-9 tool ceiling was consciously relaxed or inadvertently exceeded
- Which anti-pattern exceptions were invoked (the ADR says "only add tools with demonstrated need")
- Whether the "Agents without GitHub tools" list was reviewed and deliberately unchanged

An ADR changelog entry is not a PR description. It requires enough rationale for a future reviewer to understand the decision without reading the PR. The current entry reads as a notification, not a decision record.

### P2: Consider Fixing (Reduces Clarity)

**P2-1: The `execute` anti-pattern exception list is incomplete**

The anti-pattern section says only `implementer`, `devops`, `qa`, and `pr-comment-responder` should have `execute`. The actual agent file for `devops` uses `shell` not `execute`. The actual file for `implementer` also uses `shell`. The ADR uses `execute` throughout but the agent files use `shell`. These may be synonyms in the platform, but the ADR does not clarify this. A new engineer reading the anti-pattern rule and then checking the agent files would see no `execute` keyword and conclude the rule is satisfied when it may not be.

**P2-2: The `orchestrator` has `vscode` tool with no governance**

The orchestrator file lists `vscode` as a tool. The ADR tool categories (Core Operations, Memory, Research, GitHub, Orchestration) do not include `vscode`. Explainer also has `vscode`. There is no category for IDE-integration tools and no rationale for when they apply.

**P2-3: Complete Allocations table counts use wildcard compression inconsistently**

`cloudmcp-manager/*` and `serena/*` are each counted as 1 in the table. Individual GitHub tools are counted individually. This mixed approach makes the counts understate actual token overhead. A wildcard like `github/*` is explicitly called an anti-pattern, but `cloudmcp-manager/*` is never analyzed for how many tools it expands to. The original problem statement referenced "~58 tools" from blanket allocation. If `cloudmcp-manager/*` expands to 15+ tools, the actual effective tool counts are higher than the table shows.

**P2-4: "Agents without GitHub tools" list is stale**

The exclusion list names: `architect, critic, explainer, high-level-advisor, independent-thinker, memory, planner, qa, retrospective, roadmap, skillbook, task-generator`. This uses old agent names (`planner`, `task-generator`) and omits the 8 ungoverned agents from P0-2.

## Strengths

- The problem statement is precise: context bloat, token waste, security surface, debugging difficulty are all quantified or at least categorized.
- The GitHub toolset definition table (Category 4) is well-structured and explains the anti-pattern for blanket `github/*` clearly.
- The anti-patterns section gives concrete bad examples (allocating `github/*` when only 2 tools are needed).
- The Implementation Notes section gives actionable steps for adding new tools and agents.
- The Consequences section is honest about the maintenance burden of role-specific allocation.

## Questions for the Planner

1. Do the 4 agents with no `tools:` frontmatter (`code-reviewer`, `code-simplifier`, `comment-analyzer`, `type-design-analyzer`) inherit a platform default tool set? If so, that default set must be documented in this ADR as it directly undermines the least-privilege goal.
2. Is `shell` the same permission as `execute` in the deployment platform? If yes, update the anti-pattern text. If no, some agents have undocumented shell access.
3. Was the decision to exceed 9 tools for orchestrator, devops, and implementer a conscious trade-off, or did the counts drift without review? The answer determines whether the target range needs an "exceptions" subsection or a correction.
4. `backlog-generator` has no `edit` in its actual file but the Complete Allocations table shows `edit`. Which is authoritative? The agent file is the stated source of truth (see "More Information" section).

## Recommendations

1. Add a reconciliation pass: run a script that diffs each agent file's `tools:` list against the Complete Allocations table and fails if they diverge.
2. Add the 8 missing agents to all three tables, or document them as out-of-scope with a rationale.
3. Rename `planner` to `milestone-planner` and `task-generator` to `task-decomposer` throughout.
4. Add a decision for the tool ceiling exception: either change the target from "3-9" to "3-20" with justification, or require an explicit exception record when exceeding 9 tools.
5. Expand the PR #1517 changelog entry with per-agent rationale for each tool addition, or link to a decision record that contains it.
6. Add `shell` as an alias for `execute` in the anti-pattern section, or update all agent files to use consistent terminology.
7. Add a `vscode`/IDE category to the tool categories section.

## Approval Conditions

The ADR cannot govern what it does not describe. The two P0 issues must be resolved before the ADR can be cited as authoritative:

1. The Complete Allocations table must match the actual agent files, with explained exceptions for counts above 9.
2. All agents in `.github/agents/` must appear in the governance tables or be explicitly listed as excluded with rationale.

Until those are resolved, treat the agent files (`.github/agents/*.agent.md`) as the actual tool policy and the ADR as aspirational documentation.

**Recommended next step**: Route to milestone-planner for a reconciliation work package that audits all agent files against this ADR and produces a corrected revision.
