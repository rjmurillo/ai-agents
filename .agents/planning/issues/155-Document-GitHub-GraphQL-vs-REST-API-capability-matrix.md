---
number: 155
title: "Document GitHub GraphQL vs REST API capability matrix"
state: OPEN
created_at: 12/20/2025 10:04:38
author: rjmurillo-bot
labels: ["documentation", "area-workflows", "priority:P3"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/155
---

# Document GitHub GraphQL vs REST API capability matrix

## Problem

GitHub provides both REST and GraphQL APIs, but capability differences are not clearly documented. Some operations (like review thread resolution) are only available via GraphQL, leading to dead-ends when using REST API.

**Example**: Session 38 - PR #121 required resolving review threads. REST API endpoint `GET /repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}` is read-only; `resolveReviewThread` mutation only exists in GraphQL.

## Current Behavior

- Developers default to REST API (simpler, more familiar)
- Hit capability walls requiring GraphQL (threads, discussions, projects v2)
- No consolidated reference for "which API to use when"
- Time wasted discovering GraphQL requirement through trial and error

## Proposed Solution

Create reference guide documenting GraphQL vs REST capabilities:

### Operations Requiring GraphQL

Based on Session 38 discovery and GitHub documentation:

| Operation | REST | GraphQL | Notes |
|-----------|------|---------|-------|
| Review thread resolution | ❌ Read-only | ✅ \`resolveReviewThread\` mutation | PR #121 discovery |
| PR discussions | ⚠️ Limited | ✅ Full CRUD | Nested comments require GraphQL |
| Project boards v2 | ❌ | ✅ | Projects v2 API is GraphQL-only |
| Repository discussions | ❌ | ✅ | Discussions API is GraphQL-only |
| Advanced queries (nested data) | ⚠️ Multiple requests | ✅ Single query | GraphQL more efficient |
| Branch protection rules | ✅ | ✅ | Both supported |
| File operations | ✅ | ⚠️ Limited | REST preferred |
| Webhooks and events | ✅ | ❌ | REST only |

### When to Use Each API

**Use REST for**:
- Simple CRUD operations (create, read, update, delete)
- Webhooks and event subscriptions
- Repository management (branches, tags, releases)
- File operations (read, create, update files)
- Quick prototyping (simpler syntax)

**Use GraphQL for**:
- Review thread operations (resolve, unresolve)
- Pull request discussions (nested comments)
- Project boards v2
- Repository discussions
- Advanced queries with nested data
- Minimizing API calls (fetch related data in one query)

### Implementation Example: Review Thread Resolution

\`\`\`bash
# REST API - Read-only (cannot resolve threads)
gh api /repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}

# GraphQL - Required for resolution
gh api graphql -f query='
  mutation {
    resolveReviewThread(input: {
      threadId: "PRRT_kwDOQoWRls6cKi0O"
    }) {
      thread {
        id
        isResolved
      }
    }
  }
'
\`\`\`

## Suggested Location

Create documentation file at one of:
- `docs/github-api-capabilities.md`
- `.github/docs/api-reference.md`
- Add section to existing API documentation

## Trade-offs

**GraphQL Advantages**:
- Precise data fetching (request exactly what you need)
- Single request for related data (no over-fetching)
- Operations not available in REST (threads, discussions, projects v2)

**GraphQL Disadvantages**:
- More complex query structure (learning curve)
- Less familiar to most developers
- Harder to debug (single endpoint for all operations)

**REST Advantages**:
- Simpler syntax (just HTTP + JSON)
- More familiar to developers
- Easier to debug (one endpoint per resource)
- Better caching support (standard HTTP caching)

**REST Disadvantages**:
- Multiple requests for related data (over-fetching)
- Missing operations (threads, discussions, projects v2)
- Less efficient for complex queries

## Related

- Session 38 retrospective: GraphQL discovery
- PR #121: Review thread resolution implementation
- Skill-GitHub-GraphQL-001: GraphQL requirement skill
- GitHub GraphQL API docs: https://docs.github.com/en/graphql
- GitHub REST API docs: https://docs.github.com/en/rest

## Labels

- `documentation` - Documentation improvement
- `priority:P3` - Low priority (reference material)

---

## Comments

### Comment by @github-actions on 12/20/2025 10:05:34

<!-- AI-ISSUE-TRIAGE -->

## AI Triage Summary

> [!NOTE]
> This issue has been automatically triaged by AI agents

<details>
<summary>What is AI Triage?</summary>

This issue was analyzed by AI agents:

- **Analyst Agent**: Categorizes the issue and suggests appropriate labels
- **Roadmap Agent**: Aligns the issue with project milestones and priorities
- **Explainer Agent** (if escalated): Generates comprehensive PRD

</details>

### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | `documentation` |
| **Labels** | documentation area-infrastructure |
|  **Priority** | `P3` |
| **Milestone** | *Not assigned* |


<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["documentation", "area-infrastructure"],
  "category": "documentation",
  "confidence": 0.95,
  "reasoning": "Issue proposes creating a reference guide documenting GitHub GraphQL vs REST API capabilities based on session discoveries."
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
```json
{
  "milestone": "",
  "priority": "P3",
  "epic_alignment": "",
  "confidence": 0.85,
  "reasoning": "Documentation-only issue for reference material with no feature changes; does not align with current v1.0/v1.1 epics focused on agent consolidation and security gates",
  "escalate_to_prd": false,
  "escalation_criteria": [],
  "complexity_score": 0
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392796789)</sub>


### Comment by @coderabbitai on 12/20/2025 10:07:12

<!-- This is an auto-generated issue plan by CodeRabbit -->


### 📝 CodeRabbit Plan Mode
Generate an implementation plan and prompts that you can use with your favorite coding agent.

- [ ] <!-- {"checkboxId": "8d4f2b9c-3e1a-4f7c-a9b2-d5e8f1c4a7b9"} --> Create Plan

<details>
<summary>Examples</summary>

- [Example 1](https://github.com/coderabbitai/git-worktree-runner/issues/29#issuecomment-3589134556)
- [Example 2](https://github.com/coderabbitai/git-worktree-runner/issues/12#issuecomment-3606665167)

</details>

---

<details>
<summary><b>🔗 Similar Issues</b></summary>

**Possible Duplicates**
- https://github.com/rjmurillo/ai-agents/issues/97

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/86
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
</details>


---
<details>
<summary> 🧪 Issue enrichment is currently in open beta.</summary>


You can configure auto-planning by selecting labels in the issue_enrichment configuration.

To disable automatic issue enrichment, add the following to your `.coderabbit.yaml`:
```yaml
issue_enrichment:
  auto_enrich:
    enabled: false
```
</details>

💬 Have feedback or questions? Drop into our [discord](https://discord.gg/coderabbit) or [schedule a call](https://calendly.com/parth-coderabbit/issues-feedback)!

