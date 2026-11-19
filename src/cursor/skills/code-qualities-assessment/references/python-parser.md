# Python Parser

Python dependency counting uses Tree-sitter's Python grammar, not line matching.
It counts `import`, `from ... import`, and `from __future__ import` statements.
Statements inside functions, classes, `if` blocks, and `try` blocks count too.
Text in strings, docstrings, and comments does not add dependencies.
One statement counts once, even when it names several modules.
Dynamic imports such as `__import__("x")` and `importlib.import_module("x")` count 0.
The regex this replaced skipped them too.
Statements joined by `;` on one line count separately.
The regex this replaced counted lines, so `import os; import requests` was one dependency.

Standard-library statements are reported but not scored.
A statement is standard only when every module it names is standard.
Relative imports, such as `from .json import x`, are first-party and scored.
Other quality scores retain their existing heuristics.

Install these packages into the Python environment that runs the scanner.
System Pythons on Debian, Ubuntu, and Homebrew refuse a bare pip install (PEP 668).
Use a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install tree-sitter==0.26.1 tree-sitter-python==0.25.0
```

With uv, run `uv pip install tree-sitter==0.26.1 tree-sitter-python==0.25.0`.
Then run the scanner with that environment's Python.
To scan C# or TypeScript as well, also install `tree-sitter-c-sharp==0.23.5` or `tree-sitter-typescript==0.23.2`.

The scanner imports these packages only when assessing Python source.
Missing packages, parser startup failures, and Python the grammar cannot parse exit 1 without a report.
In regression mode, an unparsable file at the base revision also exits 1.
The scanner never installs packages or falls back to regex.

## Grammar limits

The scanner pins `tree-sitter-python==0.25.0`.
It parses Python 3.14 syntax, including PEP 695 type parameters, PEP 701 f-strings,
PEP 758 unparenthesized `except` lists, template strings, `match`, and `except*`.
Known gap: Python 3.15 `lazy import` statements do not parse.
The grammar also accepts some invalid Python, such as a Python 2 `print "x"` statement.
Exit 1 therefore means the grammar rejected the file, not that the file is invalid Python.
A file the grammar cannot parse fails the scan with exit 1.
The error names the file and the pinned grammar.
The scanner does not guess a count for such a file.
Fix the file's syntax, or wait for a grammar release that supports the feature.

## Dependency admission

Each grammar import lowers the scanner's own coupling score by one point.
The repository can admit the Python parser's dependencies through
`pythonParserDependencyAdmission` in its quality configuration.
This admission applies only to rjmurillo/ai-agents#7436's scanner transition.
The raw coupling score remains `7.0 -> 6.0`, with its regression diagnostic.
The base already holds the C# and TypeScript parser imports.
JSON keeps the raw regression and records the fixed record under `python_parser_dependency_admission`.
Exit 0 means admitted, not a raw pass; the review adapter returns `WARN`.
Other regressions, evidence loss, and new-file threshold failures still block.
The admission becomes inactive once the comparison base includes these dependencies.
