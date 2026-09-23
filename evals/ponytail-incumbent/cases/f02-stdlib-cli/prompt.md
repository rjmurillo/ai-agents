---
name: f02-stdlib-cli
tags: [code, ponytail-owned]
max_turns: 3
allowed_tools: []
---

Add command-line options to this Python 3.14 script: a required `--input` path and a `--verbose` flag that turns on debug output. The project has no runtime dependencies and wants to keep it that way. Reply with the complete updated script in one fenced code block.

```python
def main() -> int:
    path = "data.csv"
    with open(path, encoding="utf-8") as handle:
        rows = handle.read().splitlines()
    print(f"{len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
