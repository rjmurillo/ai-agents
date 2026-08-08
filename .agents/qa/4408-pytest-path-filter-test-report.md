# Test Report: Issue #4408, pytest path filter covers rule/instruction trees

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | 21 |
| Passed | 21 |
| Failed | 0 |
| Skipped | 0 |
| Duration | 0.49s |

## Command

```text
uv run pytest tests/ci/test_pytest_paths_filter_covers_episodes.py -v --tb=short
```

## Requirement Coverage

| Requirement | Test(s) | Status |
|-------------|---------|--------|
| Filter names each root explicitly | `test_the_filter_names_each_rule_input_root` x3 | [PASS] |
| Every tracked file under 3 roots is selected | `test_the_filter_covers_every_tracked_rule_input` x3 (77 files) | [PASS] |
| Unrelated session Markdown stays unselected | `test_the_filter_still_skips_tracked_session_markdown` (58 files) | [PASS] |
| Workflow YAML remains declarative (no branching logic added) | Diff inspection: only list entries and comments added to filters block | [PASS] |
| Positive evidence | 6 parametrized tests confirm selection of all 77 tracked inputs | [PASS] |
| Negative evidence | Session log control confirms 0/58 selected | [PASS] |
| Edge/structural evidence | `TestSelected` class (6 tests) validates matcher model including dot-dirs, mismatches, empty patterns | [PASS] |
| Mutation: delete roots killed | Parent evidence: removing any root causes test failure | [PASS] |
| Mutation: replace with `**/*.md` killed | Parent evidence: widens filter, session control fails | [PASS] |
| Mutation: comment-only survives | Parent evidence: non-functional change does not break tests | [PASS] |

## Reconciliation

```text
Promised: path filter selects .claude/rules, .github/instructions, src/copilot-cli/instructions;
          unrelated .agents/sessions/*.md unselected; no branching logic; positive/negative/edge/mutation tests
Delivered: 3 root globs added to filter; 77/77 tracked inputs selected; 0/58 session MD selected;
           workflow diff is declarative (list entries + comments only); 21 tests cover all categories
Gap: none
Result: PASS
```

## Status

**QA COMPLETE**

## Verdict

[PASS]. Implementation satisfies all acceptance criteria. The filter is scoped, declarative, and tested from both positive and negative perspectives with structural mutation evidence from parent run.
