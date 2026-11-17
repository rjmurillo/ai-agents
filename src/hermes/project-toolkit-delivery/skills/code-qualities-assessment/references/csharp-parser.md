# C# Parser

C# dependency counting uses Tree-sitter's C# grammar, not line matching.
It counts namespace, alias, static, and global directives.
Resource declarations, comments, and strings do not add dependencies.
Other languages and quality scores retain their existing heuristics.

Install these packages into the Python environment that runs the scanner:

Run `python3 -m pip install tree-sitter==0.26.1 tree-sitter-c-sharp==0.23.5`.

The scanner imports these packages only when assessing C# source.
Missing packages or C# syntax errors exit 1 without a passing report.
The scanner never installs packages or falls back to regex.

The repository can explicitly admit the parser's two dependencies through
`csharpParserDependencyAdmission` in its quality configuration.
This admission applies only to rjmurillo/ai-agents#7406's scanner transition.
The raw coupling score remains `10.0 -> 8.0`, with its regression diagnostic.
JSON retains the regression and records the scoped maintainer authorization.
Exit 0 means admitted, not a raw pass; the review adapter returns `WARN`.
Other regressions, evidence loss, and new-file threshold failures still block.
The admission becomes inactive once the comparison base includes these dependencies.
