---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4817-qa-analyst-contract-follow-up.json
qaCommit: 4060b157e8afd732129ddc620ac71f43601bb5e7
---

# Test Report: PR #4817 -- Analyst Contract Follow-up

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 149 |
| Passed | 149 |
| Failed | 0 |
| Skipped | 0 |
| Duration | 1.17s |

## Scope

PR #4817 hardens the analyst contract test suite with:

1. Retrieval guard (`_is_affirmative_directive`): requires analyst as grammatical
   subject (not hyphenated prefix), tool as direct verb argument (not in
   subordinate when/where/if clauses), rejects mixed-actor comma/conjunction
   clauses via new-actor-verb detection.
2. Routing validator (`_validate_routing_table`): parses ALL tables in document,
   validates tool bindings for allowed extra paths and non-path aliases, rejects
   unrecognized non-path alternatives.

## Test Execution

```text
tests/test_analyst_skill_resolution.py ........... 99 passed
tests/build_scripts/test_github_url_routing_contract.py ........... 50 passed
Total: 149 passed in 1.17s
```

## Reconciliation

```text
Promised: subordinate-clause boundary, non-analyst prefix, mixed-actor detection,
  multi-table parsing, tool-binding validation, non-path rejection
Delivered:
  - test_tool_in_when_clause_rejected (fixture 41)
  - test_tool_non_analyst_prefix_rejected (fixture 42)
  - test_tool_comma_mixed_actors_rejected (fixture 43)
  - test_tool_and_mixed_actors_rejected (fixture 44)
  - test_tool_comma_compliance_bot_rejected (fixture 45)
  - test_routing_table_rejects_non_path_alternative
  - test_routing_table_rejects_duplicate_across_tables
  - test_routing_table_rejects_wrong_extra_path_tool
  - test_routing_table_rejects_bare_alias_wrong_tool
Gap: None
Result: PASS
```

## Status

**QA COMPLETE**

## Test Results

### Passed

All 149 tests passed at exact commit 1f776d469ed765603a9a92accf7ab09a2ec94e97.

Key negative controls proving detection:

Retrieval guard (new):
- `test_tool_in_when_clause_rejected`: tool in subordinate 'when' not direct arg
- `test_tool_non_analyst_prefix_rejected`: hyphenated 'non-analyst' rejected
- `test_tool_comma_mixed_actors_rejected`: comma-separated mixed actors
- `test_tool_and_mixed_actors_rejected`: conjunction mixed actors
- `test_tool_comma_compliance_bot_rejected`: compliance-bot mixed actor

Routing validator (new):
- `test_routing_table_rejects_non_path_alternative`: "run shell commands" rejected
- `test_routing_table_rejects_duplicate_across_tables`: cross-table dupes caught
- `test_routing_table_rejects_wrong_extra_path_tool`: wrong tool binding caught
- `test_routing_table_rejects_bare_alias_wrong_tool`: arbitrary tool binding caught

### Failed

None.
