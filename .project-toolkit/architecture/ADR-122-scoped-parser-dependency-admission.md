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
7. Use the same parser approach for JavaScript, TypeScript, Python, and PowerShell.
   Each language is follow-on work in its own change.
   The C# record admits only the C# transition; item 8 admits TypeScript separately.
   A later parser import can trip the coupling gate; it needs its own admission decision.
8. Admit the TypeScript parser transition from issue #7435 as its own record.
   Add one fixed `typescriptParserDependencyAdmission` record to the scanner's admission table.
   The table holds only fixed in-code records, so the Rationale rejection of a generic framework still holds.
   Records chain: each pins the prior head score and import set, so parser changes merge one at a time.
   It requires base 8.0, head 7.0, and a comparable delta of -1.0.
   Python's AST must identify exactly `tree_sitter`, `tree_sitter_c_sharp`, and `tree_sitter_typescript`.
   The maintainer authorized it on 2026-11-18, quoted verbatim in a comment on issue #7435:
   "LGTM. Ship. agent- environment is optional. Package add approved".
   Items 1, 3, 4, and 5 apply to it. Item 2 applies with this record's scores and imports.
   Each record admits only its own transition; neither admits the other's.
   The review adapter keeps its own copy of both records.
   Exits 10 and 11 report `FAIL` before any record is read.
   On exit 0, a comparison that carries any record reports `WARN` only if exactly one record is present and valid.
   Otherwise it reports `UNKNOWN`.
   `tree-sitter-typescript` joins item 6 as a permanent scanner dependency.

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
Revisit the rejected generic framework if a record copy drifts, or before a third record lands.
The scanner's own coupling reaches 7.0, the floor of a "reasonable" import count.
The next parser import drops it to 6.0; that admission must accept the lower score.
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
The parser imports run inside functions, not at module load.
ADR-121 rule 2 scans only module-load imports, so no allowance entry applies.
The record grants no GitHub review approval.
Each record is inactive once the comparison base already contains its imports.

### Reversibility

Removing the configuration restores the ordinary coupling rejection.
Removing the admission implementation and adapter support reverses the policy change.
No data migration or installed-plugin mutation is required.

No removal is planned, because the parser dependencies are permanent design.
After the TypeScript change merges, main contains all three parser imports.
Each record matches only when the merge base sits exactly one parser step behind.
A base older than both parsers gives 10.0 to 7.0, which no record admits and which stays blocked.
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
