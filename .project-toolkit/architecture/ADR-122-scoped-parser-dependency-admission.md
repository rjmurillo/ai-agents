---
id: ADR-122
status: accepted
date: 2026-11-18
decision-makers:
  - rjmurillo
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-122: Admit Parser Dependencies Without Hiding Their Coupling

## Status

Accepted. The panel reached consensus after the scope-evidence correction.
The debate appears in `.project-toolkit/critique/ADR-122-debate-log.md`.
Publication still requires ordinary review, hooks, and protected CI.
On 2026-11-18, an amendment recorded the parser dependencies as permanent design.
A second 2026-11-18 amendment made the admission a fixed list, one record per grammar.
It added the Python record for issue #7436.

## Context

Issue #7406 requires C# directives to differ from resource declarations.
The maintainer selected a language parser rather than regex.
On 2026-11-16, its two external imports lowered scanner coupling from 10.0 to 8.0.
The unchanged regression tolerance rejects this transition with exit 10.
The maintainer authorized a scoped policy change: "waiver, full send."
That instruction grants neither GitHub approval nor permission to bypass protections.
On 2026-11-18, the maintainer ruled that the parser dependencies are permanent design.
They are not a temporary waiver, and no time bound applies.
Issue #7436 moves Python to Tree-sitter, so a second grammar import lands.
Each grammar import lowers scanner coupling by one point, past the 0.5 tolerance.
Issue #7436 offered three options; option A was this shared admission list.
On 2026-11-18, the maintainer answered that option comment: "LGTM. Ship."
The same reply approved the package: "Package add approved."

## Decision

1. Keep fixed admission records in the `parserDependencyAdmissions` list in `.qualityrc.json`.
   Each record states issue, file, imports, scores, maintainer, date, and instruction.
   Each entry must equal one record built into the scanner, listed once.
   The retired `csharpParserDependencyAdmission` key is a configuration error.
2. Limit admission to the canonical scanner's modified-file coupling transition.
   Require the record's base and head scores and their comparable delta.
   Python's AST must identify exactly the record's imports as external.
   The C# record requires 10.0 to 8.0 with `tree_sitter` and `tree_sitter_c_sharp`.
   The Python record requires 8.0 to 7.0 and adds `tree_sitter_python`.
3. Keep actual dependency counts, scores, regressions, and the original diagnostic.
   Attach the matched record to the JSON comparison as `parser_dependency_admission`.
   Print `ADMITTED` with the maintainer authorization.
4. Return exit 0 only when remaining policy checks succeed.
   The review adapter reports the admitted result as `WARN`, never `PASS`.
   Normal review acknowledgement remains required.
5. Keep other regressions, evidence loss, and new-file threshold failures blocking.
   Do not change global thresholds, formulas, tolerances, or required review axes.
   Do not extend admission to another repository or another quality.
6. Keep `tree-sitter`, `tree-sitter-c-sharp`, and `tree-sitter-python` as permanent scanner dependencies.
   No sunset date, retirement issue, or removal step applies to them.
7. Use the same parser approach for JavaScript, TypeScript, Python, and PowerShell.
   Each language is follow-on work in its own change.
   Python landed in issue #7436 with its own maintainer-approved record.
   No record pre-admits a later language.
   Each later grammar appends one record to the scanner, the adapter, and the config.
   That record needs its own admission decision.

## Prior Art Investigation

The scanner gates comparable regressions and new-file absolute thresholds separately.
The review adapter maps exits 10 and 11 to `FAIL`.
Its existing comment explains why ordinary failing gates cannot become warnings.
Commit `9b135a94dab9c4863252eb9a1c779f281643d899` (2026-10-18) last changed that adapter before this branch.
Commit `ede8a576fa19e2bd53b9602d7fe9d4ea2b53b46d` (2026-11-15) excluded Python stdlib imports from coupling.
Those purposes remain valid.
This decision represents the maintainer's specific parser-dependency authorization instead.

## Rationale

| Alternative | Benefit | Cost | Decision |
|---|---|---|---|
| Keep the branch blocked. | Preserve existing admission policy. | Reject the authorized parser implementation. | Not selected. |
| Increase global tolerance. | Avoid new admission code. | Permit unrelated dependency regressions. | Rejected. |
| Add a generic exception framework. | Support future policy exceptions. | Add capabilities without a present requirement. | Rejected. |
| Exclude declared parser packages from coupling. | No special case for this or later parser transitions. | Hides real dependencies that this record keeps visible in the score. | Rejected. |
| Add the fixed admission. | Preserve raw evidence and scoped authorization. | Maintain an explicit special case. | Selected for C#. |
| Add one config key and one code path per grammar. | Matches the first record's shape. | Four copies of the same check, and four config keys. | Rejected in the list amendment. |
| Keep a fixed list of per-grammar records. | One check serves every grammar; each record stays exact. | Records pin scores, so sibling grammars land in order. | Selected in the list amendment. |

## Consequences

The admission adds policy code and tests for one dependency decision.
Scanner JSON and stderr retain the raw failure evidence.
Consumers without the exact configuration keep their existing admission behavior.
A configuration that still uses the retired `csharpParserDependencyAdmission` key exits 1.
Every shipped copy of the scanner now needs both parser packages to score C#.
Without them, any scan that includes a C# file exits 1 and scores no file.
The review adapter then reports `UNKNOWN` for that axis.
C# that the pinned grammar cannot parse also exits 1.
The scanner also needs `tree-sitter` and `tree-sitter-python` to score Python.
Without them, any scan that includes a Python file exits 1 and scores no file.
Python that the pinned grammar cannot parse also exits 1, and the scan reports no file.
The replaced regex never failed a scan.
The `/review` skill launches the scanner with the ambient `python3`.
Without the packages there, its code-quality axis reports `UNKNOWN` for Python changes.
`merge_verdicts` never turns `UNKNOWN` into `PASS`.
So that consumer gets no review `PASS` on any change that touches Python.
Most system Pythons refuse a bare pip install (PEP 668), so a virtual environment is needed.
Python counting now treats each statement separately, not each line.
Statements joined by `;` count once each, and a stdlib-only statement stays unscored.
Each record pins base and head scores, so two grammars cannot land in parallel unchanged.
The second to merge rebases, re-measures, and updates its record.
The scanner now scores 7.0 on coupling, the default `coupling.min`.
The next grammar takes it to 6.0, so a config using that default fails the scanner itself.
This repository sets no coupling minimum, so its own gate is unaffected.
The C# record can no longer match, since the base now holds its imports.
It stays in all three copies as the record of that decision.
`references/csharp-parser.md` and `references/python-parser.md` give install commands and grammar limits.
The parser imports run inside functions, not at module load.
ADR-121 rule 2 scans only module-load imports, so no allowance entry applies.
The record grants no GitHub review approval.
When the comparison base already contains these dependencies, this admission is inactive.

### Reversibility

Removing the configuration restores the ordinary coupling rejection.
Removing the admission implementation and adapter support reverses the policy change.
No data migration or installed-plugin mutation is required.

No removal is planned, because the parser dependencies are permanent design.
After this decision's pull request merges, main contains both parser imports.
The record then matches only when the comparison merge base predates them.
Examples: a stacked branch, a cherry-pick, a revert and reintroduction, or an old `--base`.
The record and its admission code stay. No follow-up pull request removes them.

## Impact on Dependent Components

| Component | Required change |
|---|---|
| Canonical scanner | Validate each fixed record and preserve raw comparison evidence. |
| Review adapter | Normalize only evidence matching one built-in record to `WARN`. |
| Repository config | Lists each record in `parserDependencyAdmissions`; a test pins it equal to both copies. |
| Generated plugin copies | Regenerate from canonical scanner, adapter, and skill documentation. |
| Regression tests | Cover admission, malformed scope, other failures, and adapter conformance. |

## Confirmation

Run parser, scanner, regression, and verdict tests.
Compare actual scanner exits with and without the admission configuration.
Require normal independent review, hooks, protected CI, and merge containment.
This record authorizes no separate consumer cohesion change.
