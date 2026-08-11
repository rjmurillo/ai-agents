---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4817-qa-analyst-contract-follow-up.json
qaCommit: 3a097561bbe2a1410f5fa22e82cd1335048b7e90
---

# Test Report: PR #4817 -- Analyst Contract Follow-up

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 270 |
| Passed | 270 |
| Failed | 0 |
| Skipped | 0 |
| Duration | 0.99s |

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
tests/test_analyst_skill_resolution.py ........... 242 passed
tests/build_scripts/test_github_url_routing contract: 59 passed in 1.17s
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
Gap: See independent review
Result: PASS
```

## Status

**QA COMPLETE**

## Test Results

### Passed

All 242 targeted tests passed at exact commit 1f776d469ed765603a9a92accf7ab09a2ec94e97.

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

## PR #4817 review thread follow-up, arbitrary verbs

Copilot flagged a remaining finite-verb bypass: `The analyst retrieves cache,
compliance-bot owns pull_request_read.` was accepted because `owns` was not in
the boundary verb list. Confirmed and fixed in commit `53ed636b0f851f9b2081dedbce5d1e174669219b`.

The boundary now treats bot or agent subjects as new actors without enumerating
their verbs. Existing tool-subject and list-item controls still pass.

Verification run in this session:

```text
$ uv run --frozen pytest tests/test_analyst_skill_resolution.py -q
============================= 242 passed in 0.49s ==============================

$ uv run --frozen ruff check tests/test_analyst_skill_resolution.py
All checks passed!
```

Added negative control: `test_tool_mixed_owns_rejected`.

**Result**: PASS

## PR #4817 review thread follow-up, blockquoted code fences

Copilot flagged that `_compute_operative_lines` inspected the raw line, so a
blockquote prefix hid every fence marker and every indent from code-context
detection. Reproduced against branch head `80df0962af838bcef03fed735b05dca278d31066`:
a routing table wrapped in `> ``` ... > ``` ` parsed as four live routes, and a
blockquoted four-space indented table did the same. Either form satisfied the
production contract with no operative table.

Fixed in commit `3a097561bbe2a1410f5fa22e82cd1335048b7e90`. New
`_strip_blockquote_markers` removes `>` plus at most one following space and
preserves inner indentation, and fence and indented-code detection now run on
that normalized line. Both docstrings state which stripper each stage may use.

Verification run at the tested commit:

```text
$ uv run --frozen pytest tests/build_scripts/test_github_url_routing_contract.py \
    tests/test_analyst_skill_resolution.py -q
============================= 270 passed in 0.99s ==============================

$ uv run --frozen ruff check tests/build_scripts/test_github_url_routing_contract.py
All checks passed!

$ uv run --frozen ruff format --check tests/build_scripts/test_github_url_routing_contract.py
1 file already formatted
```

Post-fix reproduction returns zero routes for both bypass forms while the
visible blockquote table still parses.

Added negative controls:

- `test_blockquoted_fence_ignored`
- `test_blockquoted_tilde_fence_ignored`
- `test_nested_blockquoted_fence_ignored`
- `test_blockquoted_indented_code_ignored`
- `test_blockquoted_fence_does_not_hide_later_table`

**Result**: PASS
