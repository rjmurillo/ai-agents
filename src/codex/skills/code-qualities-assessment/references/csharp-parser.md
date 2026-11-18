# C# Parser

C# dependency counting uses Tree-sitter's C# grammar, not line matching.
It counts namespace, alias, static, and global directives.
Resource declarations, comments, and strings do not add dependencies.
Other languages and quality scores retain their existing heuristics.

Install these packages into the Python environment that runs the scanner.
System Pythons on Debian, Ubuntu, and Homebrew refuse a bare pip install (PEP 668).
Use a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install tree-sitter==0.26.1 tree-sitter-c-sharp==0.23.5
```

With uv, run `uv pip install tree-sitter==0.26.1 tree-sitter-c-sharp==0.23.5`.
Then run the scanner with that environment's Python.

The scanner imports these packages only when assessing C# source.
Missing packages, parser startup failures, and C# the grammar cannot parse exit 1 without a report.
The scanner never installs packages or falls back to regex.

## Grammar limits

The scanner pins `tree-sitter-c-sharp==0.23.5`.
Some valid C# does not parse with that grammar.
Known cases: a method signature split across `#if`/`#else`/`#endif`,
C# 14 `extension(string s) { ... }` blocks, and C# 14 `c?.X = 1`.
A file the grammar cannot parse fails the scan with exit 1.
The error names the file and says the file may be valid C#.
The scanner does not guess a count for such a file.
Fix the file's syntax, or wait for a grammar release that supports the feature.

The repository can explicitly admit the parser's two dependencies through
an entry in the `parserDependencyAdmissions` list in its quality configuration.
This admission applies only to rjmurillo/ai-agents#7406's scanner transition.
The raw coupling score remains `10.0 -> 8.0`, with its regression diagnostic.
JSON retains the regression under `parser_dependency_admission` and records the scoped maintainer authorization.
Exit 0 means admitted, not a raw pass; the review adapter returns `WARN`.
Other regressions, evidence loss, and new-file threshold failures still block.
The admission becomes inactive once the comparison base includes these dependencies.
See [Python parser](python-parser.md) for the list format and the Python grammar's admission.
