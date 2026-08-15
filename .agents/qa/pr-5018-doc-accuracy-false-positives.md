---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15000-fix-4948-doc-accuracy.json
qaCommit: b5b5d96591bfab0f040e5d761a1dd462984ef9a9
---

# PR 5018 QA Report: doc-accuracy false positives fix

## Scope

Validated that the compilability check now skips languages without source-symbol
extractors, eliminating false positives from ASCII diagrams and PowerShell fences.

## Evidence

| Check | Result |
|---|---|
| text fence (ASCII diagram) | No findings produced (was: unresolved_symbol) |
| powershell fence | No findings produced (was: unresolved_symbol) |
| csharp fence (positive control) | Still reports unresolved_symbol correctly |
| empty-language fence | No findings produced |
| Full test suite | 93 passed in 1.61s |
| Pre-push hooks | All passed |

## Reproduction

```bash
uv run python -m pytest tests/skills/doc-accuracy/test_doc_accuracy.py -x -q
# 93 passed in 1.61s
```

## VERDICT: PASS
