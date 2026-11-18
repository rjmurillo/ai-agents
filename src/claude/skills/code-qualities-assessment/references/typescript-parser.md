# TypeScript Parser

TypeScript dependency counting uses Tree-sitter's TypeScript grammars, not line matching.
`.ts` files use the TypeScript grammar. `.tsx` files use the TSX grammar.
JavaScript files keep their existing line heuristic.

Each of these counts as one dependency:

- `import` statements, including `import type`, side-effect imports, and `import x = require("y")`.
- `export ... from` re-exports, including `export *` and `export type { T } from`.
- `require("...")` calls.
- Dynamic `import("...")` expressions.
- Type-position imports such as `typeof import("m")` and `import("m").T`.
  They name a module just as `import type` does, so they count the same way.

Comments, strings, template literals, and `export { a }` with no source add nothing.

Install these packages into the Python environment that runs the scanner.
System Pythons on Debian, Ubuntu, and Homebrew refuse a bare pip install (PEP 668).
Use a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install tree-sitter==0.26.1 tree-sitter-typescript==0.23.2
```

With uv, run `uv pip install tree-sitter==0.26.1 tree-sitter-typescript==0.23.2`.
Then run the scanner with that environment's Python.

The scanner imports these packages only when assessing TypeScript source.
Missing packages, parser startup failures, and TypeScript the grammar cannot parse exit 1 without a report.
The scanner never installs packages or falls back to regex.

## Grammar limits

The scanner pins `tree-sitter-typescript==0.23.2`.
Some valid TypeScript does not parse with that grammar.
Known cases: `export type * from "m"` (TypeScript 5.0) and `in`/`out` variance annotations such as `type T<in out U> = U`.
A `<Type>value` cast is valid only in `.ts`; in a `.tsx` file it fails to parse, as it does in the TypeScript compiler.
A file the grammar cannot parse fails the scan with exit 1.
The error names the file and says the file may be valid TypeScript.
The scanner does not guess a count for such a file.

## Dependency admission

The repository can admit the TypeScript parser's coupling change through
`typescriptParserDependencyAdmission` in its quality configuration.
This admission applies only to rjmurillo/ai-agents#7435's scanner transition.
The raw coupling score remains `8.0 -> 7.0`, with its regression diagnostic.
Exit 0 means admitted, not a raw pass; the review adapter returns `WARN`.
Other regressions, evidence loss, and new-file threshold failures still block.
