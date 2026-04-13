# Skill-Quality-003: Shift-Left Agent Consultation

**Statement**: MUST consult 6 specialized agents post-code, pre-push for quality gates

**Context**: After implementation complete, before git push

**Evidence**: Pattern discovered 2025-12-26, prevents PR review cycles

**Atomicity**: 95% | **Impact**: 9/10

## Pattern

Run ALL 6 agents using standardized prompts BEFORE pushing code:

```python
# Agent consultation sequence (can run in parallel)
Task(subagent_type="analyst", prompt="Review changes per .github/prompts/pr-quality-gate-analyst.md")
Task(subagent_type="architect", prompt="Review changes per .github/prompts/pr-quality-gate-architect.md")
Task(subagent_type="devops", prompt="Review changes per .github/prompts/pr-quality-gate-devops.md")
Task(subagent_type="qa", prompt="Review changes per .github/prompts/pr-quality-gate-qa.md")
Task(subagent_type="roadmap", prompt="Review changes per .github/prompts/pr-quality-gate-roadmap.md")
Task(subagent_type="security", prompt="Review changes per .github/prompts/pr-quality-gate-security.md")
```

**Verification**: All 6 agents produce reports before push

**Required Agents**:
1. analyst - code quality, impact, architectural concerns
2. architect - design governance, pattern compliance
3. devops - CI/CD, infrastructure concerns
4. qa - test coverage, error handling, edge cases
5. roadmap - strategic alignment
6. security - vulnerability assessment, threat modeling

**Standardized Prompts**: Located at `.github/prompts/pr-quality-gate-{agent}.md`

## Anti-Pattern

Pushing code without agent consultation, leading to PR review cycles and rework.

## Related

- [quality-agent-remediation](quality-agent-remediation.md)
- [quality-basic-testing](quality-basic-testing.md)
- [quality-critique-escalation](quality-critique-escalation.md)
- [quality-definition-of-done](quality-definition-of-done.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
