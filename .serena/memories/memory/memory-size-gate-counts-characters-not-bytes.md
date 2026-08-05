# Skill: the memory size gate counts characters, `wc -c` counts bytes (93%)

## Statement

`validate_memory_sizes.py` fails a memory above 10,000 **characters**.
`wc -c` and `len(s.encode())` report **bytes**. On a memory carrying emoji or
any non-ASCII, the two disagree, and `wc -c` reads high.

Check size with the validator. Never with `wc -c`.

```bash
uv run --frozen python scripts/memory/validate_memory_sizes.py <path to memory>
```

## Why they diverge

`test_memory_size.py:117` computes `char_count = len(content)` on a decoded
`str` and compares it to `MAX_CHARS = 10_000` at line 130. Python's `len` on a
`str` counts code points.

UTF-8 spends three bytes on a typical emoji and two on an accented letter, so
every such character widens the gap by one or two. A memory that uses status
glyphs in a table pays the difference on every row.

## Evidence

2026-08-05. A memory measured 10,005 by `wc -c` and 9,996 by the validator.
Three emoji accounted for the nine byte spread. Reading `wc -c` as the gate
bought six unnecessary trim passes over prose that was already under the limit,
and each pass risked cutting content the memory needed.

The validator was correct the whole time. It was never run until the sixth
pass.

## Related trap in the same area

`scripts/memory/` holds `detect_stale.py`, `memory_health.py`, and
`validate_memory_sizes.py`. It does **not** hold the memory index token
regenerator, which lives at `scripts/update_memory_index_tokens.py`. Guessing
`scripts/memory/update_memory_index_tokens.py` returns "No such file", which
reads like proof the tool does not exist. It does.

That near miss is the general lesson: a single path probe cannot support an
absence claim. Search the repo before concluding a tool is missing, because
nothing downstream contradicts a wrong negative.

## Related

- [memory-size-001-decomposition-thresholds](memory-size-001-decomposition-thresholds.md), what to do once a memory is genuinely over the limit
- [serena-memory-subdirectory-convention](serena-memory-subdirectory-convention.md), the index and token regenerator workflow
