# Context output check latency

Issue #5836 records one real commit-hook run on this checkout.

Measured: 2026-09-17
Commit: `d1edeed11bde1ea92dd92d3bd62227700e8ba474`
Samples: n=1
Environment: Linux, Python 3.14.7, Lefthook 2.1.12

| Check | Observed wall time |
|---|---:|
| Full pre-commit hook | 13.05s |
| `context-output-check` job | 1.35s |
| Manifest checker, five warm direct runs | 0.14s each |

The hook ran the staged checker against 12 sources, 12 indexes, and 118
expected detail files. It found 118 detail files. The checker performed no
writes. The staged regression test detected drift when only the changed source
was staged.

Command used for the direct measurement:

```text
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python .claude/skills/context-optimizer/scripts/extract_and_index.py --check --manifest .agents/context-output-manifest.json
```
