## Skill-006: Generated Files Omit Edit Warnings (90%)

Generated `.agent.md` files omit "DO NOT EDIT" headers - AI agents consume these and human warnings add noise.

**Evidence**: PR #43

## Skill-007: Analyst vs Impact Analysis (95%)

| Agent | Output Path |
|-------|-------------|
| Analyst | `.agents/analysis/` |
| Impact Analysis (5 specialists) | `.agents/planning/impact-analysis-*.md` |

**Evidence**: PR #46

## Skill-008: Nested Code Fence Syntax (88%)

Outer fence needs more backticks than inner. 4-backtick outer with 3-backtick inner is correct CommonMark.

**Evidence**: PR #43

## Quick Dismissal

| Pattern | Action |
|---------|--------|
| Missing "DO NOT EDIT" in generated | Dismiss |
| Analyst output path confusion | Clarify directories |
| Nested fence flagged | Dismiss (valid CommonMark) |
