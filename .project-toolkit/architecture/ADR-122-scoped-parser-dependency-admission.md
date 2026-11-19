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

# ADR-122: Admit the C# Parser Dependencies Without Hiding Their Coupling

## Status

Accepted. The panel reached consensus after the scope-evidence correction.
The debate appears in `.project-toolkit/critique/ADR-122-debate-log.md`.
Publication still requires ordinary review, hooks, and protected CI.
On 2026-11-18, an amendment recorded the parser dependencies as permanent design.
A later 2026-11-18 amendment added item 8, the TypeScript admission for issue #7435.
A third 2026-11-18 amendment added item 9, the Python admission for issue #7436.
A fourth 2026-11-18 amendment recorded PowerShell's subprocess parser in item 7.

## Context

Issue #7406 requires C# directives to differ from resource declarations.
The maintainer selected a language parser rather than regex.
On 2026-11-16, its two external imports lowered scanner coupling from 10.0 to 8.0.
The unchanged regression tolerance rejects this transition with exit 10.
The maintainer authorized a scoped policy change: "waiver, full send."
That instruction grants neither GitHub approval nor permission to bypass protections.
On 2026-11-18, the maintainer ruled that the parser dependencies are permanent design.
They are not a temporary waiver, and no time bound applies.
Item 8 extends this decision to the TypeScript parser (issue #7435).
Item 9 extends it to the Python parser (issue #7436).

## Decision

1. Add one fixed `csharpParserDependencyAdmission` record to `.qualityrc.json`.
   It records issue, file, imports, scores, maintainer, date, and instruction.
   Configuration must equal the fixed admission contract, including authorization.
2. Limit admission to the canonical scanner's modified-file coupling transition.
   Require base 10.0, head 8.0, and a comparable delta of -2.0.
   Python's AST must identify exactly `tree_sitter` and `tree_sitter_c_sharp` externally.
3. Keep actual dependency counts, scores, regressions, and the original diagnostic.
   Attach the admission record separately to the JSON comparison.
   Print `ADMITTED` with the maintainer authorization.
4. Return exit 0 only when remaining policy checks succeed.
   The review adapter reports the admitted result as `WARN`, never `PASS`.
   Normal review acknowledgement remains required.
5. Keep other regressions, evidence loss, and new-file threshold failures blocking.
   Do not change global thresholds, formulas, tolerances, or required review axes.
   Do not extend admission to another repository or another quality.
6. Keep `tree-sitter` and `tree-sitter-c-sharp` as permanent scanner dependencies.
   No sunset date, retirement issue, or removal step applies to them.
7. Use the same Tree-sitter approach for JavaScript, TypeScript, and Python.
   Each language is follow-on work in its own change.
   The C# record admits only the C# transition; item 8 admits TypeScript and item 9 Python separately.
   A later parser import can trip the coupling gate; it needs its own admission decision.
   Issues #7434, #7435, and #7436 follow that approach, and each needs its own admission.
   PowerShell uses its own parser instead. The maintainer chose it for #7437 on 2026-11-18.
   The scanner runs `pwsh` as a subprocess. It adds no third-party Python import.
   So the coupling score stays the same and needs no admission.
   The reason: `tree-sitter-powershell==0.26.4` marked 8 of 63 pwsh 7.6.10 modules with errors.
   PowerShell's parser marked none of them. Evidence: #7437 comments, 2026-11-18.
8. Admit the TypeScript parser transition from issue #7435 as its own record.
   Add one fixed `typescriptParserDependencyAdmission` record to the scanner's admission table.
   The table holds only fixed in-code records, so the Rationale rejection of a generic framework still holds.
   Records chain: each pins the prior head score and import set, so parser changes merge one at a time.
   It requires base 8.0, head 7.0, and a comparable delta of -1.0.
   Python's AST must identify exactly `tree_sitter`, `tree_sitter_c_sharp`, and `tree_sitter_typescript`.
   The maintainer authorized it on 2026-11-18, quoted verbatim in a comment on issue #7435:
   "LGTM. Ship. agent- environment is optional. Package add approved".
   Items 1, 3, 4, and 5 apply to it. Item 2 applies with this record's scores and imports.
   Each record admits only its own transition; no record admits another's.
   The review adapter keeps its own copy of every record.
   Exits 10 and 11 report `FAIL` before any record is read.
   On exit 0, a comparison that carries any record reports `WARN` only if exactly one record is present and valid.
   Otherwise it reports `UNKNOWN`.
   `tree-sitter-typescript` joins item 6 as a permanent scanner dependency.
9. Admit the Python parser transition from issue #7436 as its own record.
   Add one fixed `pythonParserDependencyAdmission` record to the scanner's admission table.
   It chains after item 8: it requires base 7.0, head 6.0, and a comparable delta of -1.0.
   Python's AST must identify exactly `tree_sitter`, `tree_sitter_c_sharp`,
   `tree_sitter_python`, and `tree_sitter_typescript`.
   The maintainer authorized it on 2026-11-18, quoted verbatim in issue #7436 comment 6995934831:
   "LGTM. Ship. agent- environment is optional. Package add approved".
   Items 1, 3, 4, and 5 apply to it. Item 2 applies with this record's scores and imports.
   Item 8's rules on exit codes, one record per comparison, and the adapter copy apply unchanged.
   `tree-sitter-python` joins item 6 as a permanent scanner dependency.
   This is the third record, which the Consequences named as the revisit trigger.
   A shared record list was weighed as option A in issue #7436 comment 6991092132.
   On 2026-11-18, the coordinator of the four Tree-sitter issues kept one record per grammar.
   Issue #7436 comment 6995934831 records that choice.
   That keeps each sibling rebase mechanical: append one record in the item 8 shape.

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
| Add the fixed admission. | Preserve raw evidence and scoped authorization. | Maintain an explicit special case. | Selected. |

## Consequences

Each admission adds policy code and tests for one dependency decision.
Each later language adds one record in three files: the scanner, the review adapter, and `.qualityrc.json`.
Item 9 is the third record, which reached the earlier revisit trigger; item 9 records the outcome.
Revisit the rejected generic framework if a record copy drifts, or if a grammar needs a record shape other than item 8's.
A fifth record is already planned under item 7, so a record count is no longer a useful trigger.
The scanner's own coupling reaches 7.0, the floor of a "reasonable" import count.
The next parser import drops it to 6.0; that admission must accept the lower score.
Item 9 is that admission: the scanner now scores 6.0, below the default `coupling.min` of 7.
A consumer config on that default fails the scanner itself; this repository sets no coupling minimum.
Scanner JSON and stderr retain the raw failure evidence.
Consumers without the exact configuration keep their existing admission behavior.
Every shipped copy of the scanner now needs both parser packages to score C#.
Without them, any scan that includes a C# file exits 1 and scores no file.
The review adapter then reports `UNKNOWN` for that axis.
C# that the pinned grammar cannot parse also exits 1.
`references/csharp-parser.md` gives the install command and the grammar limits.
Scoring TypeScript needs `tree-sitter` and `tree-sitter-typescript`.
Without them, a scan that includes a `.ts` or `.tsx` file exits 1.
`references/typescript-parser.md` gives the install command and the grammar limits.
Scoring Python needs `tree-sitter` and `tree-sitter-python`.
Without them, a scan that includes a `.py` file exits 1.
The `/review` skill launches the scanner with the ambient `python3`.
Without the packages there, its code-quality axis reports `UNKNOWN` for Python changes.
`merge_verdicts` never turns `UNKNOWN` into `PASS`, so that consumer gets no review `PASS` on Python changes.
Python the pinned grammar cannot parse also exits 1; the replaced regex never failed a scan.
Python counting is per statement, not per line, so statements joined by `;` count separately.
`references/python-parser.md` gives the install command and the grammar limits.
Any scan that includes a PowerShell file needs `pwsh` 7 or later on PATH.
Without it, or on a PowerShell syntax error or a 60 second timeout, the scan exits 1.
Each PowerShell file costs one `pwsh` process, about 0.65 seconds.
PowerShell resolves `using module` and `using assembly` targets while it parses.
On Windows a UNC target would open a network share and could send credentials.
So the scanner rewrites every ASCII `using` to an inert command name before parsing.
The count then comes from those commands, and no target is ever resolved.
`references/powershell-parser.md` gives the requirement and its limits.
The parser imports run inside functions, not at module load.
ADR-121 rule 2 scans only module-load imports, so no allowance entry applies.
The record grants no GitHub review approval.
Each record is inactive once the comparison base already contains its imports.

### Reversibility

Removing the configuration restores the ordinary coupling rejection.
Removing the admission implementation and adapter support reverses the policy change.
No data migration or installed-plugin mutation is required.

No removal is planned, because the parser dependencies are permanent design.
After the Python change merges, main contains all four parser imports.
Each record matches only when the merge base sits exactly one parser step behind.
A base two or more parser steps behind, such as 8.0 to 6.0, matches no record and stays blocked.
Examples: a stacked branch, a cherry-pick, a revert and reintroduction, or an old `--base`.
The record and its admission code stay. No follow-up pull request removes them.

## Impact on Dependent Components

| Component | Required change |
|---|---|
| Canonical scanner | Validate the fixed admission and preserve raw comparison evidence. |
| Review adapter | Normalize only valid admitted evidence to `WARN`. |
| Generated plugin copies | Regenerate from canonical scanner, adapter, and skill documentation. |
| Regression tests | Cover admission, malformed scope, other failures, and adapter conformance. |

## Confirmation

Run parser, scanner, regression, and verdict tests.
Compare actual scanner exits with and without the admission configuration.
Require normal independent review, hooks, protected CI, and merge containment.
This record authorizes no separate consumer cohesion change.
