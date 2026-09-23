---
type: llm
---

Pass only if the reply makes `pyproject.toml` (or one other single place) the only authored version and derives the other at runtime or build time, for example with `importlib.metadata.version("pkg")`, so the two cannot disagree. It should also say the release-branch comparison check becomes unnecessary or can be deleted. A reply whose main change is another detector fails.
