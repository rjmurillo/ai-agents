# Skill-PR-006: Reviewer Signal Quality

**Statement**: Prioritize reviewers by historical actionability rate.

**Atomicity**: 96% | **Validated**: 14 PRs

| Priority | Reviewer | Signal Rate | Action |
|----------|----------|-------------|--------|
| **P0** | cursor[bot] | **100%** (28/28) | Process immediately |
| **P1** | Human reviewers | N/A | Domain expertise |
| **P2** | Copilot | **90%** (17/19) | Review with priority |
| **P2** | coderabbitai[bot] | ~50% (163 comments) | Review carefully |
| **P3** | gemini-code-assist[bot] | **0%** (0/5 on PR 308) | Check exclusion context |

**Comment Type Actionability**:

| Type | Rate | Examples |
|------|------|----------|
| Bug reports | ~90% | cursor[bot] bugs, type errors |
| Missing coverage | ~70% | Test gaps, edge cases |
| Style suggestions | ~20% | Formatting, naming |
| Summaries | 0% | CodeRabbit walkthroughs |
