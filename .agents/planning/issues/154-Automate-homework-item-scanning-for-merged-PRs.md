---
number: 154
title: "Automate homework item scanning for merged PRs"
state: OPEN
created_at: 12/20/2025 10:03:50
author: rjmurillo-bot
labels: ["enhancement", "area-workflows", "priority:P2", "automation"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/154
---

# Automate homework item scanning for merged PRs

## Problem

Deferred work items ("TODO", "Deferred to follow-up", "future improvement") accumulate in PR review comments but are not systematically tracked. Manual scanning is time-consuming and inconsistent.

**Evidence**: Session 39 - Manual scan of 27 PRs found 5 actionable homework items (~20% hit rate). Consistent pattern across different reviewers and timeframes justifies automation.

## Current Behavior

- Deferred work mentioned in PR comments
- No automatic issue creation for follow-up tasks
- Manual scanning required to discover homework items
- Risk of forgotten improvements and tech debt accumulation

## Success Metrics from Manual Scan

| Metric | Value |
|--------|-------|
| PRs scanned | 27 |
| Actionable items found | 5 |
| Hit rate | 18.5% (~20%) |
| Time per PR | ~3.3 minutes |
| Total manual effort | ~90 minutes |

**Items Found**:
- Issue #144: Path list duplication (PR #100)
- Issue #145: Duplicate job names (PR #100)
- Issue #146: Convert bash to PowerShell (PR #100)
- Issue #149: Pre-commit validation (PR #94)
- Issue #150: Extract verdict logic (PR #76)

## Proposed Solution

Create GitHub Action triggered on PR merge to automatically scan for homework items and create tracking issues.

### Search Patterns

\`\`\`regex
- "Deferred to follow-up"
- "future improvement"
- "A future improvement could be"
- "TODO" (in comments, not code)
- "follow-up task"
- "out of scope for this PR"
- "addressed in a future PR"
\`\`\`

### False Positives to Filter

- Generic "TODO" in bot failure messages
- Nitpick comments already addressed
- "should be" suggestions in passing reviews (not actionable)

### Implementation Outline

\`\`\`yaml
name: Homework Scanner
on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  scan:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Fetch PR Comments
        id: fetch
        env:
          GH_TOKEN: \${{ secrets.GITHUB_TOKEN }}
        run: |
          gh api repos/\${{ github.repository }}/pulls/\${{ github.event.pull_request.number }}/comments \
            | jq -r '.[].body' > comments.txt
          
          gh api repos/\${{ github.repository }}/pulls/\${{ github.event.pull_request.number }}/reviews \
            | jq -r '.[].body' >> comments.txt
      
      - name: Search for Homework
        id: search
        run: |
          grep -i "deferred to follow-up\|TODO\|future improvement\|out of scope" comments.txt \
            > homework.txt || true
          
          if [ -s homework.txt ]; then
            echo "found=true" >> \$GITHUB_OUTPUT
          else
            echo "found=false" >> \$GITHUB_OUTPUT
          fi
      
      - name: Create Issues
        if: steps.search.outputs.found == 'true'
        env:
          GH_TOKEN: \${{ secrets.GITHUB_TOKEN }}
        run: |
          # Parse homework items and create issues
          # Each issue includes:
          # - Source PR link
          # - Source comment ID
          # - Quoted deferred work description
          # - Suggested labels (enhancement, maintenance, etc.)
\`\`\`

## Issue Template for Created Items

\`\`\`markdown
## Source

From PR #123, comment by @reviewer:
https://github.com/owner/repo/pull/123#discussion_r456789

> Deferred to follow-up: Extract duplicated logic to reusable function

## Current State

[What exists today]

## Proposed Solution

[What the deferred work suggests]

## Related Files

- [File paths mentioned]

---
🤖 Created by Homework Scanner from PR #123
\`\`\`

## ROI Analysis

| Scenario | Manual | Automated |
|----------|--------|-----------|
| Upfront effort | 0 hours | 4 hours (build action) |
| Per-PR effort | 3.3 min | 0 min |
| Break-even | N/A | ~73 PRs |
| Annual volume | 50-100 PRs | 50-100 PRs |
| Annual savings | N/A | 2.75-5.5 hours |

**Justification**: 20% hit rate + consistent pattern + low maintenance cost = worthwhile automation.

## Related

- Session 39: Manual homework scanning results
- Session 38 retrospective: ROI analysis
- Skill-Maintenance-002: Search patterns skill
- Skill-Maintenance-003: Automation justification skill
- Issues #144-150: Examples of found homework items

## Labels

- `enhancement` - New feature
- `area-workflows` - GitHub Actions
- `priority:P2` - Medium priority (quality of life improvement)
- `automation` - Build/CI automation

---

## Comments

### Comment by @coderabbitai on 12/20/2025 10:04:58

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
- https://github.com/rjmurillo/ai-agents/issues/148

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/116
- https://github.com/rjmurillo/ai-agents/issues/108
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/ai-agents#20 - feat: Phase 2 CWE-78 Incident Remediation - Operational Capabilities [merged]
rjmurillo/ai-agents#32 - feat: Ideation Workflow, Prioritization Frameworks, and CodeRabbit Optimization [merged]
rjmurillo/ai-agents#52 - feat: MCP config sync utility and pre-commit architecture documentation [merged]
rjmurillo/ai-agents#98 - chore(deps): configure Dependabot for GitHub Actions updates [closed]
rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [closed]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
- [rjmurillo](https://github.com/rjmurillo)
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

### Comment by @github-actions on 12/20/2025 10:07:42

<!-- AI-PRD-GENERATION -->

## 📋 Product Requirements Document

> [!IMPORTANT]
> This PRD was automatically generated based on issue triage escalation.
> **Complexity Score**: 7/12 ()
> **Escalation Criteria**: feature_request, multi_phase_work

<details>
<summary>📖 About this PRD</summary>

This PRD was generated by the **Explainer Agent** after the issue was flagged
for detailed analysis. The document is designed to be self-contained - it can
be passed to a separate AI agent instance for implementation without additional
context.

**PRD Depth Levels**:
- **Standard** (4-6): Brief analysis, clear requirements
- **Detailed** (7-9): Research section, blocking questions
- **Comprehensive** (10-12): Phased implementation, risk analysis

</details>

---

Now I have enough context. Let me create the PRD.

Unable to write to the planning directory. Let me output the PRD directly instead.

---

# PRD: Automated Homework Item Scanner

## Executive Summary

Deferred work items in PR review comments accumulate without systematic tracking. Manual scanning of 27 PRs identified 5 actionable items (18.5% hit rate) in 90 minutes. This document specifies a GitHub Action to automate homework detection and issue creation on PR merge.

| Scope | Status | Blocker |
|-------|--------|---------|
| PR comment scanning | :green_circle: READY | None |
| Homework pattern matching | :green_circle: READY | None |
| Issue creation | :green_circle: READY | None |
| False positive filtering | :yellow_circle: PARTIAL | Pattern refinement needed post-launch |

**Verdict**: READY

## Problem Statement

### Current State

| Aspect | Current Behavior |
|--------|------------------|
| Homework tracking | Manual discovery only |
| Detection method | Ad-hoc PR comment review |
| Issue creation | Manual |
| Coverage | Inconsistent |
| Time cost | 3.3 minutes per PR |

### Gap Analysis

1. **No automation**: Deferred work languishes in PR comments
2. **Inconsistent capture**: Different reviewers use different phrasing
3. **Hidden tech debt**: Follow-up items forgotten after PR merge
4. **Manual overhead**: 90 minutes for 27 PRs is unsustainable at scale

### User Impact

- **Maintainers**: Spend time manually scanning PRs for deferred work
- **Contributors**: Lose track of promised follow-up improvements
- **Codebase**: Accumulates technical debt from forgotten improvements

## Research Findings

### Primary Sources

**GitHub Actions Documentation** (CONFIRMED)
- `pull_request` event with `types: [closed]` triggers on merge
- `github.event.pull_request.merged == true` filters merged PRs only
- `gh api` provides access to PR comments and reviews

**Existing Workflow Patterns** (CONFIRMED)
- Repository uses composite actions (`ai-review`)
- PowerShell scripts exist in `scripts/` directory
- GitHub skill scripts exist in `.claude/skills/github/scripts/`

### Empirical Data

| Pattern | Occurrences in Sample |
|---------|----------------------|
| "Deferred to follow-up" | 2 |
| "future improvement" | 2 |
| "TODO" (in comment context) | 1 |
| "out of scope" | 0 |

**Confidence Level**: CONFIRMED based on Session 39 manual scan evidence.

## Proposed Solution

### Phase 1: Core Scanner (Status: READY)

**Estimated Effort**: M (4 hours)
**Blockers**: None

| Task | Description |
|------|-------------|
| 1.1 | Create workflow file `.github/workflows/homework-scanner.yml` |
| 1.2 | Implement PR comment fetching via `gh api` |
| 1.3 | Implement pattern matching with grep |
| 1.4 | Create issue from detected homework items |
| 1.5 | Add workflow tests |

### Phase 2: False Positive Filtering (Status: READY)

**Estimated Effort**: S (2 hours)
**Blockers**: Depends on Phase 1 completion

| Task | Description |
|------|-------------|
| 2.1 | Add exclusion patterns for bot messages |
| 2.2 | Filter "nitpick" comments that were addressed |
| 2.3 | Skip generic "should be" suggestions in approvals |

## Functional Requirements

### FR-1: Workflow Trigger

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Workflow triggers on PR merge to main branch | Workflow runs when PR with `merged == true` closes |
| FR-1.2 | Workflow does not trigger on closed-without-merge | Verify `merged == true` condition prevents false triggers |

### FR-2: Comment Collection

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Fetch all PR review comments | API call retrieves `/pulls/{number}/comments` |
| FR-2.2 | Fetch all PR review bodies | API call retrieves `/pulls/{number}/reviews` |
| FR-2.3 | Handle PRs with no comments gracefully | Workflow exits cleanly with no issue created |

### FR-3: Pattern Matching

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | Match "Deferred to follow-up" case-insensitive | Pattern matches regardless of capitalization |
| FR-3.2 | Match "future improvement" case-insensitive | Pattern matches regardless of capitalization |
| FR-3.3 | Match "TODO" in comment context | Pattern matches TODO in review text |
| FR-3.4 | Match "out of scope for this PR" | Pattern matches scope deferral language |
| FR-3.5 | Match "addressed in a future PR" | Pattern matches future work language |

### FR-4: Issue Creation

**Priority**: P0

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-4.1 | Create issue with source PR link | Issue body contains PR number and URL |
| FR-4.2 | Include quoted comment text | Issue body contains the matched comment |
| FR-4.3 | Include comment author | Issue body mentions reviewer who wrote the comment |
| FR-4.4 | Add scanner footer | Issue ends with "Created by Homework Scanner" attribution |
| FR-4.5 | Apply appropriate labels | Issue receives `homework`, `tech-debt` labels |

### FR-5: False Positive Filtering

**Priority**: P1

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-5.1 | Exclude bot-generated comments | Comments from `github-actions[bot]` are skipped |
| FR-5.2 | Exclude resolved threads | Comments in resolved review threads are skipped |
| FR-5.3 | Exclude nitpick suggestions | Comments starting with "nitpick:" are skipped |

## Non-Functional Requirements

### Consistency

- Follow existing workflow patterns in `.github/workflows/`
- Use `gh` CLI for GitHub API operations (matches existing workflows)
- Use bash for primary implementation (matches `ai-review` action)

### Testability

- Pester tests for pattern matching logic
- Integration test with mock PR data
- Manual verification against known homework PRs (#100, #94, #76)

### Documentation

- Update `docs/` with workflow description
- Add inline comments explaining pattern choices
- Document false positive handling in workflow file

## Technical Design

### Workflow Configuration

```yaml
# .github/workflows/homework-scanner.yml
name: Homework Scanner

on:
  pull_request:
    types: [closed]
    branches: [main]

permissions:
  contents: read
  issues: write
  pull-requests: read

jobs:
  scan:
    name: Scan for Homework Items
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - name: Checkout repository
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683

      - name: Fetch PR Comments
        id: fetch
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          # Fetch review comments (inline comments on diff)
          gh api "repos/${{ github.repository }}/pulls/${PR_NUMBER}/comments" \
            --jq '.[] | {author: .user.login, body: .body, url: .html_url}' \
            > /tmp/review-comments.json

          # Fetch review bodies (overall review text)
          gh api "repos/${{ github.repository }}/pulls/${PR_NUMBER}/reviews" \
            --jq '.[] | select(.body != null and .body != "") | {author: .user.login, body: .body, url: .html_url}' \
            >> /tmp/review-comments.json

          # Combine into single text file for grep
          jq -r '.body' /tmp/review-comments.json > /tmp/all-comments.txt

      - name: Search for Homework Patterns
        id: search
        run: |
          PATTERNS=(
            "deferred to follow-up"
            "future improvement"
            "TODO"
            "out of scope for this PR"
            "addressed in a future PR"
            "follow-up task"
            "A future improvement could be"
          )

          # Build grep pattern
          GREP_PATTERN=$(printf '%s\|' "${PATTERNS[@]}" | sed 's/\\|$//')

          # Search case-insensitive
          if grep -i "$GREP_PATTERN" /tmp/all-comments.txt > /tmp/homework-matches.txt 2>/dev/null; then
            echo "found=true" >> $GITHUB_OUTPUT
            echo "Homework items found:"
            cat /tmp/homework-matches.txt
          else
            echo "found=false" >> $GITHUB_OUTPUT
            echo "No homework items found"
          fi

      - name: Filter False Positives
        if: steps.search.outputs.found == 'true'
        run: |
          # Remove bot comments
          grep -v "github-actions\[bot\]" /tmp/review-comments.json > /tmp/filtered.json || true

          # Remove nitpick comments
          jq 'select(.body | test("^nitpick:"; "i") | not)' /tmp/filtered.json \
            > /tmp/homework-final.json || true

      - name: Create Homework Issues
        if: steps.search.outputs.found == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_URL: ${{ github.event.pull_request.html_url }}
        run: |
          # Read matched comments and create issues
          while IFS= read -r line; do
            AUTHOR=$(echo "$line" | jq -r '.author')
            BODY=$(echo "$line" | jq -r '.body')
            URL=$(echo "$line" | jq -r '.url')

            # Extract the specific homework sentence
            HOMEWORK_TEXT=$(echo "$BODY" | grep -i -E \
              "deferred to follow-up|future improvement|TODO|out of scope|addressed in a future" \
              | head -1)

            if [ -n "$HOMEWORK_TEXT" ]; then
              ISSUE_TITLE="Homework: $(echo "$HOMEWORK_TEXT" | head -c 60)..."

              ISSUE_BODY=$(cat <<EOF
## Source

From PR #${PR_NUMBER} (${PR_TITLE}), comment by @${AUTHOR}:
${URL}

> ${HOMEWORK_TEXT}

## Context

Original comment:
\`\`\`
${BODY}
\`\`\`

## Proposed Action

[To be determined by assignee]

---
:robot: Created by Homework Scanner from PR #${PR_NUMBER}
EOF
)

              gh issue create \
                --title "$ISSUE_TITLE" \
                --body "$ISSUE_BODY" \
                --label "homework" \
                --label "tech-debt"

              echo "Created issue for homework item from @${AUTHOR}"
            fi
          done < /tmp/homework-final.json
```

### Label Configuration

```yaml
- name: Ensure Labels Exist
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    gh label create "homework" \
      --description "Deferred work from PR reviews" \
      --color "FBCA04" \
      --force || true

    gh label create "tech-debt" \
      --description "Technical debt to address" \
      --color "D93F0B" \
      --force || true
```

## Implementation Plan

### Decision Tree

```text
Is PR merged?
├── NO → Exit workflow (no action)
└── YES → Fetch PR comments
         ├── No comments found → Exit (no action)
         └── Comments found → Search for homework patterns
              ├── No matches → Exit (no action)
              └── Matches found → Filter false positives
                   ├── All filtered → Exit (no action)
                   └── Valid items remain → Create issues
```

### Phase 1 Tasks

1. Create `.github/workflows/homework-scanner.yml`
2. Test on existing PRs (#100, #94, #76) using `workflow_dispatch` trigger
3. Validate issue creation format
4. Remove `workflow_dispatch` trigger for production

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| High false positive rate | Medium | Medium | Start with strict patterns, expand iteratively |
| Duplicate issues created | Low | Low | Phase 3 adds deduplication check |
| Missing homework items | Medium | Low | Monitor and expand patterns based on misses |
| API rate limiting | Low | Low | Single workflow run, minimal API calls |

## Success Metrics

| Metric | Target |
|--------|--------|
| False positive rate | Less than 20% |
| Coverage of deferred items | Greater than 80% of manually identified items |
| Time to issue creation | Less than 2 minutes from merge |
| Workflow failure rate | Less than 5% |

## Blocking Questions

None. All information required for implementation is available.

## Open Questions (Non-Blocking)

1. **Q**: Should issues be assigned to the PR author or left unassigned?
   - **Hypothesis**: Leave unassigned, let maintainers triage

2. **Q**: Should the scanner create one issue per match or one consolidated issue?
   - **Hypothesis**: One issue per distinct homework item for trackability

---

**Document Version**: 1.0 | **Complexity Score**: 6 (Standard) | **Priority**: P2

**Recommended Next Steps**: Route to **implementer** for Phase 1 workflow creation.

---

<sub>📋 Generated by [AI PRD Generation](https://github.com/rjmurillo/ai-agents) · [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392787271)</sub>



### Comment by @github-actions on 12/20/2025 10:07:44

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
| **Category** | `enhancement` |
| **Labels** | enhancement area-workflows |
|  **Priority** | `P2` |
| **Milestone** | v1.1 |
| **PRD Escalation** | Generated (see below) |

<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-workflows"],
  "category": "enhancement",
  "confidence": 0.95,
  "reasoning": "Issue proposes a new GitHub Actions workflow to automate scanning merged PRs for deferred work items"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
Based on my review of the roadmap and handoff context, I can now provide the alignment assessment for this GitHub issue.

```json
{
  "milestone": "v1.1",
  "priority": "P2",
  "epic_alignment": "",
  "confidence": 0.70,
  "reasoning": "Quality-of-life automation with clear ROI (73 PR break-even), aligns with maintainability focus of v1.1 but not tied to any existing epic",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "multi_phase_work"],
  "complexity_score": 7
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20392787271)</sub>


