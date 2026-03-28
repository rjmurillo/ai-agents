# Analysis: ADR-003 Evidence and Feasibility Review

## 1. Objective and Scope

**Objective**: Verify factual accuracy of ADR-003 claims: tool counts, statistics, GitHub toolset totals, and PR #1517 changelog adequacy.
**Scope**: Five specific claims in ADR-003 at `/home/user/ai-agents/.agents/architecture/ADR-003-agent-tool-selection-criteria.md`. Source-of-truth agent files at `.github/agents/*.agent.md`. Git history for PR #1517 traceability. GitHub MCP tool enumeration from live session context.

---

## 2. Context

ADR-003 documents the role-specific tool allocation strategy for the multi-agent system. It was updated on 2026-03-25 to reflect PR #1517, which added GitHub search tools to six agents. The ADR claims a reduction from ~58 or ~77 tools down to 3-9 per agent, with specific statistics in a summary table.

---

## 3. Approach

**Methodology**: Manual verification against source-of-truth files. Git log inspection for commit traceability. Python-based tool counting from frontmatter YAML. Live GitHub MCP tool enumeration from session context.

**Tools Used**: Read (agent files, ADR), Bash (git log, git show, Python counting), session MCP tool registry.

**Limitations**: GitHub CLI unavailable (unauthenticated). PR #1517 and Issue #1511 web content not directly accessible. GitHub MCP toolset breakdown (context, repos, issues, etc.) verified only by summing the ADR's own table and comparing to live tool count; official GitHub MCP Server documentation not fetched.

---

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| PR #1517 commit exists in git history | `git log --grep="1517"` | High |
| PR #1517 touched exactly 6 agent files | `git show 6c2fdcd --stat` | High |
| Actual tool counts differ from ADR table | `.github/agents/*.agent.md` frontmatter | High |
| ADR toolset table sums to 59, not 77 | ADR-003 table arithmetic | High |
| Live GitHub MCP session exposes 50 tools | System prompt deferred tool list | Medium |
| ADR statistics (min 4, max 15, avg 7.4) are wrong | Python count against source files | High |

### Verified Tool Counts (Source of Truth: `.github/agents/`)

| Agent | ADR Claims | Actual Count | Delta |
|-------|-----------|--------------|-------|
| analyst | 11 | 18 | +7 |
| architect | 5 | 5 | 0 |
| backlog-generator | 11 | 10 | -1 |
| critic | 5 | 5 | 0 |
| devops | 13 | 18 | +5 |
| explainer | 4 | 6 | +2 |
| high-level-advisor | 5 | 5 | 0 |
| implementer | 13 | 16 | +3 |
| independent-thinker | 8 | 8 | 0 |
| memory | 5 | 5 | 0 |
| orchestrator | 15 | 20 | +5 |
| pr-comment-responder | 7 | 7 | 0 |
| qa | 6 | 6 | 0 |
| retrospective | 6 | 6 | 0 |
| roadmap | 4 | 4 | 0 |
| security | 11 | 12 | +1 |
| skillbook | 5 | 5 | 0 |

Agents with zero delta: 10 of 17 (59%). Agents where ADR is wrong: 7 of 17 (41%).

### Statistics Comparison

| Metric | ADR Claims | Actual |
|--------|-----------|--------|
| Minimum | 4 | 4 (roadmap) |
| Maximum | 15 | 20 (orchestrator) |
| Average | 7.4 | 9.2 |
| Agent count in table | 19 (incl. task-generator) | 17 in source-of-truth files with tools |

The ADR statistics are based on a stale snapshot that predates PR #1517. The PR added 18 tool entries across 6 agents, raising the maximum by 5 and the average by 1.8.

### PR #1517 Scope Verification

ADR changelog states: "Added GitHub search tools to research-capable agents (analyst, orchestrator, devops, implementer, security, backlog-generator)."

Git evidence from commit `6c2fdcd`:

```
.github/agents/analyst.agent.md           | 2 ++
.github/agents/backlog-generator.agent.md | 5 +++++
.github/agents/devops.agent.md            | 4 ++++
.github/agents/implementer.agent.md       | 2 ++
.github/agents/orchestrator.agent.md      | 4 ++++
.github/agents/security.agent.md          | 1 +
6 files changed, 18 insertions(+)
```

The six agents named in the changelog match the six files changed. The scope description is accurate.

### GitHub Toolset Count (~77 tools claim)

The ADR's own toolset breakdown table sums to 59, not 77:

| Toolset | ADR Count |
|---------|-----------|
| context | 3 |
| repos | 17 |
| issues | 8 |
| pull_requests | 10 |
| users | 1 |
| actions | 14 |
| code_security | 2 |
| dependabot | 2 |
| secret_protection | 2 |
| **Total** | **59** |

The live GitHub MCP session exposes 50 discrete tools. Neither figure matches the ADR's claim of ~77. The claim uses a tilde (~) indicating approximation, but 59 and 50 are both materially lower than 77. The actual GitHub MCP Server tool count (not accessible without GitHub CLI auth) may differ from both figures. The ~77 claim is unverified and internally inconsistent with the ADR's own table.

The anti-pattern note at line 311 also cites ~77 tools adding "30-40KB of tool definitions." No source is given for the KB figure. This is unverified.

### Changelog Adequacy for PR #1517

The changelog entry is:

```
| 2026-03-25 | Added GitHub search tools to research-capable agents
              (analyst, orchestrator, devops, implementer, security,
              backlog-generator) | PR #1517, Issue #1511 |
```

What the changelog captures correctly:
- Date matches commit date (2026-03-25)
- All six agents named match the six files changed
- PR reference is traceable via git log

What the changelog omits:
- The statistics table (min/max/avg) was not updated to reflect the new counts
- The "Complete Tool Allocations" table still shows pre-PR counts (analyst: 11, devops: 13, orchestrator: 15, implementer: 13)
- The ADR description says "target: 3-9 tools per agent" but post-PR, six agents exceed 9 tools (analyst: 18, devops: 18, orchestrator: 20, implementer: 16, backlog-generator: 10, security: 12)
- No rationale given for why specific search tools were chosen per agent (e.g., analyst got `search_users`; security did not get `search_repositories`)

---

## 5. Results

1. PR #1517 scope description in changelog: accurate.
2. ADR tool count table: stale for 7 of 17 agents; counts reflect pre-PR state.
3. Statistics (min 4, max 15, avg 7.4): minimum is correct; maximum and average are wrong by 5 and 1.8 respectively.
4. GitHub ~77 tools claim: internally inconsistent. ADR's own table sums to 59; live session shows 50.
5. "3-9 tools per agent" design target: violated by 6 agents post-PR (range is now 4-20).

---

## 6. Discussion

The ADR was partially updated for PR #1517. The changelog entry correctly names agents and references. However, the tool count table, statistics block, and design target range were not updated. This is a documentation drift problem: the source-of-truth files advanced while the ADR's summary tables did not.

The ~77 GitHub tools figure appears in two places: the toolset definition preamble and the anti-pattern section. Neither cite an external source. The ADR's own table contradicts this claim. The figure likely originated from an earlier version of the GitHub MCP Server and was not rechecked during drafting.

The "3-9 tools" target in the chosen option description conflicts with post-PR reality. Six agents now hold 10-20 tools. The ADR needs either a range correction (e.g., "4-20 tools, median 6") or a rationale for why research-capable agents are exempt from the 9-tool ceiling.

---

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Update the statistics block (min/max/avg) to match current source files | False data in an accepted ADR misleads future reviewers | 15 minutes |
| P0 | Update the "Complete Tool Allocations" table with actual post-PR counts | 7 rows are wrong; table is labeled as the record of allocation | 30 minutes |
| P1 | Correct or remove the ~77 GitHub tools claim; replace with verified count | Internal inconsistency (table sums to 59; live session shows 50) undermines credibility | 30 minutes |
| P1 | Update "target: 3-9 tools" to reflect the actual post-PR range | Six agents exceed 9 tools; the design target is now aspirational, not descriptive | 15 minutes |
| P2 | Add rationale for per-agent search tool selection differences | analyst gets `search_users`, security does not; neither is explained | 20 minutes |

---

## 8. Conclusion

**Verdict**: CONCERNS

**Confidence**: High

**Rationale**: The PR #1517 scope claim in the changelog is accurate and traceable. However, the ADR's statistics block, tool count table, design target range, and GitHub tool total are all inconsistent with the source-of-truth files. These are documentation drift issues, not evidence of an invalid decision. The underlying architectural decision (role-specific allocation) is sound and implemented. The ADR needs a targeted sync pass before it can be cited as accurate.

### User Impact

- **What changes for you**: Any agent or process relying on the ADR's tool count table will get wrong numbers. The statistics block cannot be cited as fact.
- **Effort required**: Four focused edits totaling under 90 minutes to correct tables and stats.
- **Risk if ignored**: Future ADR reviews will reach wrong conclusions about tool budget compliance. The "3-9 tools" guard rail is functionally dead if six agents exceed it without documented rationale.

---

## 9. Appendices

### Sources Consulted

- `/home/user/ai-agents/.agents/architecture/ADR-003-agent-tool-selection-criteria.md`
- `/home/user/ai-agents/.github/agents/*.agent.md` (17 files with tools frontmatter)
- `git log --grep="1517"` and `git show 6c2fdcd` (commit evidence for PR #1517)
- Session MCP deferred tool registry (GitHub MCP tools enumeration)

### Data Transparency

- **Found**: PR #1517 commit with full diff, all 17 agent tool lists, ADR toolset table, git log tracing changelog to commit
- **Not Found**: Official GitHub MCP Server documentation listing canonical ~77 tool count; PR #1517 and Issue #1511 web content (gh CLI unauthenticated); kb-size data for tool definitions
