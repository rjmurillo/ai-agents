---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4817-qa-analyst-contract-follow-up.json
qaCommit: a701e9982f5719d02cae7912419667084cc1ad6a
---

# Test Report: PR #4817 -- Explicit Analyst Attribution and Strict Routing Validation

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 122 |
| Passed | 122 |
| Failed | 0 |
| Skipped | 0 |
| Duration | 0.75s |

## Scope

PR #4817 fixes two High defects from independent review of #4787 / #4570:

1. Retrieval guard accepts actorless/passive directives. Fixed by requiring "analyst" as grammatical actor in `_is_affirmative_directive`.
2. Routing parser uses substring matching. Fixed with `_parse_routing_table` returning a multimap and `_validate_routing_table` enforcing exact canonical patterns.

## Test Execution

```text
tests/test_analyst_skill_resolution.py ........... 83 passed
tests/build_scripts/test_github_url_routing_contract.py ........... 39 passed
Total: 122 passed in 0.75s
```

## Reconciliation

```text
Promised: 4 negative controls (fixtures 23-26), 1 routing duplicate rejection, strict actor attribution, exact canonical routing
Delivered: test_tool_bare_imperative_rejected, test_tool_passive_voice_rejected, test_tool_compliance_bot_rejected, test_tool_analyst_negated_rejected, test_routing_table_rejects_duplicate_rows, test_tool_analyst_as_object_rejected, test_tool_analyst_may_not_rejected, test_tool_analyst_will_not_rejected, test_routing_table_rejects_suffix_pattern, test_routing_table_rejects_noncanonical_placeholder, test_routing_table_validates_mcp_prefixed_tools
Gap: None
Result: PASS
```

## Status

**QA COMPLETE**

## Test Results

### Passed

All 122 tests passed. Key new negative controls:

- `test_tool_bare_imperative_rejected`: Rejects directives without explicit analyst actor.
- `test_tool_passive_voice_rejected`: Rejects passive voice attribution.
- `test_tool_compliance_bot_rejected`: Rejects arbitrary agent actors.
- `test_tool_analyst_negated_rejected`: Rejects negated analyst modalities.
- `test_tool_analyst_as_object_rejected`: Rejects analyst as grammatical object.
- `test_tool_analyst_may_not_rejected`: Rejects "may not" negation.
- `test_tool_analyst_will_not_rejected`: Rejects "will not" negation.
- `test_routing_table_rejects_duplicate_rows`: Validates unique routing rows.
- `test_routing_table_rejects_suffix_pattern`: Validates exact pattern matching.
- `test_routing_table_rejects_noncanonical_placeholder`: Validates canonical placeholders.
- `test_routing_table_validates_mcp_prefixed_tools`: Validates MCP prefix handling.

### Failed

None.

### Skipped

None.

## Gaps Identified

None.
