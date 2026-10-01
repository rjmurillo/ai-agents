# Skill Sidecar Learnings: Orchestrator

**Last Updated**: 2026-09-29
**Sessions Analyzed**: 1

## Observations (MED confidence)

- Subagents correctly refuse owner approvals relayed by the orchestrator. Evidence: decision D5 for PR #5992 `--approve-untrusted-config`. The orchestrator runs owner-gated commands itself and records the approval on the PR. (Session claude-session-0191QTCyqXgwVXfiZgDSfTcn, 2026-09-29)
