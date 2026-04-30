## Summary

REQ-003 multi-tool artifact build system. Generates native Copilot CLI outputs from canonical `.claude/` sources. Aftermath of PR #1773 regression + PR #1795 P0 fix.

**This PR is DRAFT for review of:**
1. **Spec** (`REQ-003`) — 12 acceptance criteria, 11 architectural decisions, verified-facts table from Copilot CLI docs
2. **Plan** — 30 tasks across 7 milestones (M0 ADR gate + M1-M6 implementation), risk register, kill criteria
3. **ADR-006 Amendment** — config-data exception with 7 conditions, 6/6 multi-agent consensus

No production code shipped yet. M0 gate (this PR) unblocks M1 implementation.

## Specification References

| Type | Reference | Description |
|------|-----------|-------------|
| **Spec** | [`.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md`](.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md) | EARS requirements with verified Copilot CLI facts |
| **Plan** | [`.agents/plans/active/req-003-multi-tool-artifact-build.md`](.agents/plans/active/req-003-multi-tool-artifact-build.md) | 6 milestones, 30 tasks, ~23 person-days |
| **ADR Amendment** | [`.agents/architecture/ADR-006-thin-workflows-testable-modules.md`](.agents/architecture/ADR-006-thin-workflows-testable-modules.md) (Amendment 2026-04-28) | Config-data exception |
| **Debate log** | [`.agents/critique/ADR-006-amendment-2026-04-28-debate-log.md`](.agents/critique/ADR-006-amendment-2026-04-28-debate-log.md) | Round 1 + Round 2 multi-agent consensus |
| **Triggering incident** | [`.agents/incidents/2026-04-27-pir-plugin-manifest-schema-1773.md`](.agents/incidents/2026-04-27-pir-plugin-manifest-schema-1773.md) | PR #1773 PIR (motivates schema gates) |
| **Anthropic docs** | https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference | Source of truth for Copilot CLI plugin schema |

## Type of Change

- [x] Documentation update (spec + plan + ADR amendment)
- [x] Architecture decision (ADR-006 amendment, multi-agent consensus)
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Infrastructure/CI change (this PR ships none; M3-M6 will)

## Changes

- **`.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md`** (428 lines): EARS-format spec. 12 acceptance criteria (REQ-003-001 through -012), 11 locked architectural decisions (D1-D11), CVA matrix, verified-facts table with citations, 4 residual open questions tagged for empirical post-merge testing, 7 risks pre-flagged.
- **`.agents/plans/active/req-003-multi-tool-artifact-build.md`** (149 lines): 7-milestone execution plan (M0 ADR gate + M1-M6 implementation). 30 atomic tasks, 14S/10M/3L sizing, ~23 person-days. Risk register with R1-R10 (matcher shim whitespace bypass, applyTo unknown CLI consumption, etc.). M5 kill criteria documented. Single critical path; no inter-milestone parallelism.
- **`.agents/architecture/ADR-006-thin-workflows-testable-modules.md`**: Amendment 2026-04-28 (165 added lines). 7 conditions gate the config-data exception. Anchors original ADR-006 rationale verbatim. Forward-looking policy with grandfathering for existing `templates/platforms/*.yaml` files. Reversibility assessment + confirmation method.
- **`.agents/critique/ADR-006-amendment-2026-04-28-debate-log.md`**: Multi-agent debate log. Round 1: 6 agents (architect APPROVE_WITH_CHANGES, critic NEEDS_REVISION, independent-thinker/security/analyst D&C, advisor ACCEPT). Round 2: all blocking findings addressed; 6/6 ACCEPT consensus.
- **`.agents/sessions/2026-04-28-session-1761-...json`**: Protocol-compliant session log.

## Verification

```text
$ python3 scripts/validate_session_json.py .agents/sessions/2026-04-28-session-1761-*.json
[PASS] (after session-end)

$ ls .agents/critique/ADR-006-amendment-2026-04-28-debate-log.md
exists  # ADR architect-gate hook satisfied

$ wc -l .agents/specs/requirements/REQ-003-multi-tool-artifact-build.md \
        .agents/plans/active/req-003-multi-tool-artifact-build.md \
        .agents/architecture/ADR-006-thin-workflows-testable-modules.md
~428 spec / ~149 plan / ~417 ADR (after amendment)
```

## Test plan

- [x] Spec EARS-formatted with testable acceptance criteria
- [x] Plan tasks each have explicit acceptance criterion + REQ trace
- [x] ADR amendment passes multi-agent debate (6/6 consensus, all P0 findings resolved)
- [x] Debate log artifact exists at `.agents/critique/` (satisfies architect-gate hook)
- [x] Session log validates locally
- [ ] CI green on this PR (no code shipped; doc-only)
- [ ] Reviewer approves spec scope, plan sequencing, ADR amendment
- [ ] After merge: M1 implementation unblocked

## Open for review

This is a **draft PR** asking for review of three artifacts before any code lands:

1. **Spec scope** — are the 12 acceptance criteria right? Any missing? Out-of-scope items correct?
2. **Plan sequencing** — single critical path M0→M6; no parallelism. M5 (hooks + matcher shim) is highest risk. Kill criteria documented. Acceptable?
3. **ADR amendment** — 7 conditions for config-data YAML exception. Multi-agent debate shows 6/6 consensus after Round 2 hardening. Worth merging?

After merge, M1 implementation (`templates/platforms/copilot-cli.yaml` schema + `validate_templates_schema.py`) ships as a separate PR.

## Related

- Aftermath of: PR #1773 (regression) + PR #1795 (P0 fix; Customer plugin install was broken)
- Branch name `fix/plugin-manifest-schema-1793` from PR #1795 referred to internal tracking; not a GH issue

🤖 Generated with [Claude Code](https://claude.com/claude-code)
