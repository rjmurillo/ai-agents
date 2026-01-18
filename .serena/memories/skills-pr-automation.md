# PR Automation Skills

## Skill-PR-Automation-001: Bot Author Awareness Gap

**Statement**: Bot PR authors need @mention to detect feedback requiring action

**Context**: When AI Quality Gate or similar workflow posts feedback to bot-authored PRs

**Evidence**: PR #121 in rjmurillo/ai-agents - GitHub Copilot created PR but was unaware of AI Quality Gate feedback until explicitly @mentioned. Issue #152 created to address this gap.

**Atomicity**: 95%

**Source**: Session 38 retrospective (2025-12-20)

---

## Skill-PR-Automation-002: Bot Notification Syntax

**Statement**: Use `@${{ github.event.pull_request.user.login }}` to notify PR author in workflow comments

**Context**: When posting workflow feedback requiring author action

**Evidence**: Issue #152 implementation guidance for AI Quality Gate enhancement

**Implementation Example**:
```yaml
- name: Post feedback with @mention
  run: |
    # When CRITICAL_FAIL or actionable feedback
    gh issue comment ${{ github.event.pull_request.number }} \
      --body "@${{ github.event.pull_request.user.login }} Action required: [feedback content]"
```

**Atomicity**: 92%

**Source**: Session 38 retrospective (2025-12-20)

---

## Key Pattern

Bot authors (copilot-swe-agent, dependabot, github-actions) do NOT:
- Monitor PR activity notifications
- Check for review comments
- Respond to workflow status changes

They ONLY respond to:
- Direct @mentions in comments
- Assignment changes
- Explicit issue/PR assignments

**Solution**: Always @mention the PR author when posting actionable feedback from workflows.

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-agent-workflow-phase3](skills-agent-workflow-phase3.md)
- [skills-agent-workflows](skills-agent-workflows.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-analysis](skills-analysis.md)
