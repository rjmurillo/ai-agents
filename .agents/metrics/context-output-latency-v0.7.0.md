# Context output check latency

Issue #5836 records one real commit-hook run on this checkout.

Measured: 2026-09-18
Commit: `928160a22b1eac5747c8b1fa88514765ded28e79`
Samples: hook n=1, direct n=5
Environment: Linux, Python 3.14.7, Lefthook 2.1.12

| Check | Observed wall time |
|---|---:|
| Full pre-commit hook | 2.85s |
| `context-output-check` job | 1.31s |
| Manifest checker, five warm direct runs | 0.1421s mean, 0.1390s to 0.1449s |

The real commit hook ran with `lefthook.yml` staged. The staged checker covered
12 sources, 12 indexes, and 113 expected detail files. It found 113 detail
files and performed no writes. The staged regression test detected drift when
only the changed source was staged.

Command used for the direct measurement:

```text
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python .claude/skills/context-optimizer/scripts/extract_and_index.py --check --manifest .agents/context-output-manifest.json
```
