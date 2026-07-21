---
status: recorded
process: adr-review multi-agent debate (6 reviewers)
adr: ADR-041
---

# ADR-041 Amendment Debate Log

Multi-agent review of the ADR-041 amendment retiring CodeQL Tier 3 (the
`invoke_codeql_quick_scan.py` PostToolUse hook), session 3295. The amendment
invokes ADR-041's own re-evaluation clause (2026-07-16), which pre-authorizes
deprecating an unused tier by amendment: "If negative ROI or unused, create
amendment ADR to deprecate and simplify to CI-only."

## Votes

| Reviewer | Vote |
| --- | --- |
| architect | ACCEPT |
| critic | ACCEPT_WITH_CHANGES |
| security | ACCEPT |
| independent-thinker | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |

No REJECT votes. Consensus: 6/6 accept. The critic's two required changes
were applied before recording acceptance.

## Major findings and resolutions

1. critic: the amendment must not leave the broadly stale `docs/codeql-*.md`
   references dangling. Either clean them in scope or cite a tracking issue.
   RESOLVED: filed #3296 to track the full PowerShell-to-Python plus
   three-tier-to-two-tier docs overhaul, added a staleness banner to each of
   the three docs, and cited #3296 in the amendment's "Documentation drift"
   paragraph.
2. critic: the preserved Tier-3 sections in the ADR body could read as still
   authoritative. Note explicitly that they are historical and superseded.
   RESOLVED: added a "Historical record" paragraph to the amendment stating
   the original three-tier body is preserved for provenance but superseded by
   the amendment; the Operational Status table marks Tier 3 Retired.

## Factual verification (analyst)

All six load-bearing claims verified TRUE:

- The hook is registered nowhere: absent from `settings.json`,
  `dispatch_groups.json`, and the vendored Copilot hook surface.
- The hook is imported only by its own test (`test_invoke_codeql_quick_scan.py`).
- The re-evaluation clause quote is exact at ADR-041 line 328.
- `codeql-analysis.yml` runs CodeQL on pull requests (Tier retained).
- `invoke_codeql_scan.py` (the on-demand skill path) is intact and untouched.
- #3219 (portable auth-edit security hook backlog) is referenced consistently.

## Disposition

Accept as amended. This debate log is the pre-commit evidence; the PR-side
adr-review workflow and maintainer acceptance remain the merge gate. Refs
ADR-041, #3295, #3197, #3296.
