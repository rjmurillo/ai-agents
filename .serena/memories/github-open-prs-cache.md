# GitHub Open PRs Cache

**Last Updated**: 2025-12-23T21:00:00Z
**TTL**: 30 minutes
**Next Refresh**: After 2025-12-24T00:00:00Z (or on PR state change)

## Cache-Aside Pattern

Before querying GitHub API for open PRs:
1. Read this memory
2. Check if `now < Next Refresh`
3. If FRESH: use cached data
4. If STALE: query API, update this file

## Open Pull Requests (10 total)

| PR | Title | Branch | Author |
|----|-------|--------|--------|
| #315 | feat(skill): add ADR review skill | feat/adr-review | rjmurillo |
| #313 | fix(pr-maintenance): remove exit code 1 for blocked PRs | copilot/investigate-workflow-failure | copilot-swe-agent |
| #310 | docs(adr): add model routing policy to minimize false PASS | docs/adr-017 | rjmurillo |
| #308 | feat(memory): implement ADR-017 tiered memory index architecture | memory-automation-index-consolidation | rjmurillo-bot |
| #301 | docs: autonomous PR monitoring prompt and retrospective | combined-pr-branch | rjmurillo-bot |
| #300 | docs(retrospective): autonomous PR monitoring session analysis | docs/autonomous-pr-monitoring-retrospective | rjmurillo-bot |
| #299 | docs: add autonomous PR monitoring prompt | docs/autonomous-monitoring-prompt | rjmurillo-bot |
| #285 | perf: Add -NoProfile to pwsh invocations for 72% faster execution | feat/284-noprofile | rjmurillo-bot |
| #269 | docs(orchestrator): add Phase 4 pre-PR validation workflow | copilot/add-pre-pr-validation-workflow | copilot-swe-agent |
| #255 | feat(github-skill): enhance skill for Claude effectiveness | feat/skill-leverage | rjmurillo-bot |

## Quick Lookup

**By Author**:
- rjmurillo: #315, #310
- rjmurillo-bot: #308, #301, #300, #299, #285, #255
- copilot-swe-agent: #313, #269

**Ready for Review**: #308, #315, #310
**Draft/WIP**: #301, #300, #299, #285, #269, #255
