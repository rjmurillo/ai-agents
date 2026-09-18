# Context output check latency

Issue #5836 records one real commit-hook run on this checkout.

Measured: 2026-09-18
Commit: `e7a386d3b3fa3e514a698fd53bb046c6fd8f19fe`
Samples: hook n=1, direct n=5
Environment: Linux, Python 3.14.7, Lefthook 2.1.12

| Check | Observed wall time |
|---|---:|
| Full pre-commit hook | 10.40s |
| `context-output-check` job | 1.31s |
| Manifest checker, five warm direct runs | 0.1392s mean, 0.1382s to 0.1406s |

The hook ran the staged checker against 12 sources, 12 indexes, and 113
expected detail files. It found 113 detail files. The checker performed no
writes. The staged regression test detected drift when only the changed source
was staged.

Command used for the direct measurement:

```text
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python .claude/skills/context-optimizer/scripts/extract_and_index.py --check --manifest .agents/context-output-manifest.json
```
