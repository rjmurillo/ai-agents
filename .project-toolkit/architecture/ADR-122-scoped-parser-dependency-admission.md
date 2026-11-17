---
id: ADR-122
status: accepted
date: 2026-11-16
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

## Context

Issue #7406 requires C# directives to differ from resource declarations.
The maintainer selected a language parser rather than regex.
On 2026-11-16, its two external imports lowered scanner coupling from 10.0 to 8.0.
The unchanged regression tolerance rejects this transition with exit 10.
The maintainer authorized a scoped policy change: "waiver, full send."
That instruction grants neither GitHub approval nor permission to bypass protections.

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
| Add the fixed admission. | Preserve raw evidence and scoped authorization. | Maintain an explicit special case. | Selected. |

## Consequences

The admission adds policy code and tests for one dependency decision.
Scanner JSON and stderr retain the raw failure evidence.
Consumers without the exact configuration retain their existing gate behavior.
The record grants no GitHub review approval.
When the comparison base already contains these dependencies, this admission is inactive.

### Reversibility

Removing the configuration restores the ordinary coupling rejection.
Removing the admission implementation and adapter support reverses the policy change.
No data migration or installed-plugin mutation is required.

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
