---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-4817-qa-analyst-contract-follow-up.json
qaCommit: e448e4a76169c67d226e1dd3feb14e1ebc72a712
---

# Test Report: PR #4817 -- Analyst Contract Follow-up

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 277 |
| Passed | 277 |
| Failed | 0 |
| Skipped | 0 |
| Duration | 1.01s |

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
tests/test_analyst_skill_resolution.py: 202 passed
tests/build_scripts/test_github_url_routing_contract.py: 75 passed
Total: 277 passed in 1.01s
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

## Post-base-refresh verification

The PR head was merged with `origin/main` at
`e9c548a090dc7c2ffb91be9eea249e4d7f4bf01a`, producing tested commit
`e448e4a76169c67d226e1dd3feb14e1ebc72a712`. The base refresh introduced no
source edits to the PR changes.

```text
$ uv run --frozen pytest -q tests/test_analyst_skill_resolution.py \
    tests/build_scripts/test_github_url_routing_contract.py
============================= 277 passed in 1.01s ==============================
```

**Result**: PASS

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

Fixed in commit `3a097561bbe2a1410f5fa22e82cd1335048b7e90`, re-verified at
`cf622b0ce47eeb2e616ae59335df2640836e6263` after dropping the empty
`tests/skills/doc-accuracy/__init__.py` that main had already deleted. New
`_strip_blockquote_markers` removes `>` plus at most one following space and
preserves inner indentation, and fence and indented-code detection now run on
that normalized line. Both docstrings state which stripper each stage may use.

Verification run at the tested commit:

```text
$ uv run --frozen pytest tests/build_scripts/test_github_url_routing_contract.py \
    tests/test_analyst_skill_resolution.py tests/skills/doc-accuracy/ -q
============================= 321 passed in 5.97s ==============================

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

## PR #4817 review thread follow-up, table interruption and fronted tool phrase

Two more findings from the rescan, both reproduced before the fix.

Table interruption: a fence or a multi-line HTML comment inside a table only
skipped that row, so orphan `| ... |` rows after the interruption completed the
route set.

```text
before: {'/pull/<n>': [...], '/issues/<n>': [...], '/actions/runs/<id>': [...],
         '/actions/runs/<id>/job/<jid>': [...]}
after:  {'/pull/<n>': ['pull_request_read']}
```

Fronted tool phrase: `_is_affirmative_directive` searched the whole pre-verb
prefix, so `The compliance-bot calls pull_request_read before the analyst
retrieves cache.` returned True. The prefix must now match the anchored
`Using` or `Via <tool>, the analyst ...` shape.

Fixed in commit `3cb3b798e1241981a1d10b1fb21b0ad4c97866fe`.

Verification at the tested commit:

```text
$ uv run --frozen pytest tests/test_analyst_skill_resolution.py \
    tests/build_scripts/test_github_url_routing_contract.py tests/skills/doc-accuracy/ -q
============================= 328 passed in 1.26s ==============================

$ uv run --frozen ruff check tests/test_analyst_skill_resolution.py \
    tests/build_scripts/test_github_url_routing_contract.py
All checks passed!
```

Added controls:

- `test_fence_interrupting_table_ends_it`
- `test_html_comment_interrupting_table_ends_it`
- `test_table_after_interruption_parses_on_its_own_header`
- `test_pre_analyst_tool_by_other_actor_rejected`
- `test_pre_analyst_tool_after_other_actor_clause_rejected`
- `test_using_tool_comma_analyst_accepted`
- `test_via_tool_analyst_accepted`

**Result**: PASS
