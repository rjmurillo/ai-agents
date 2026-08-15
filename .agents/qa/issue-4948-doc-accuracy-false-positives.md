---
qaCommit: 42c419a6883d5295098b48d00d114ddfb435b4f2
qaSessionLog: .agents/sessions/2026-08-14-session-14711-fix-4948-doc-accuracy-false-positives.json
qaVerdict: PASS
---

# QA Report: Issue #4948 - Doc Accuracy False Positives

## Objective

Verify the fix for `doc-accuracy` false positives on text fences, Mermaid fences, PowerShell examples, and unmapped code claims.

## Tests

- `uv run pytest tests/skills/doc-accuracy/test_doc_accuracy.py -q`
- `uv run ruff check .claude/skills/doc-accuracy/scripts/doc_accuracy.py src/copilot-cli/skills/doc-accuracy/scripts/doc_accuracy.py tests/skills/doc-accuracy/test_doc_accuracy.py`
- Temp fixture reproduction with `doc_accuracy.py --target <tmp> --format summary --severity-threshold high`

## Results

| Check | Result |
|-------|--------|
| Targeted pytest | PASS, 83 tests |
| Ruff | PASS |
| Reproduction before fix | FAIL, exit 10 with 2 claims and 8 high findings |
| Reproduction after fix | PASS, exit 0 with 0 claims and 0 findings |

## Notes

- Text fences and Mermaid fences no longer produce claims.
- PowerShell claims are skipped by Phase 3 when loaded from cached artifacts.
- Code example claims no longer inherit a fallback source file when no symbol matches.
