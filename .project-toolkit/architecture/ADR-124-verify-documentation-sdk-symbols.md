---
id: ADR-124
status: proposed
date: 2026-11-20
decision-makers:
  - rjmurillo
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-124: Verify Documentation SDK Symbols

## Status

Proposed. Round 1 blocked, and the owner then narrowed the scope.
Panel round 2 and owner acceptance are required before implementation.
The debate appears in `.project-toolkit/critique/ADR-124-debate-log.md`.
Issue [#7501](https://github.com/rjmurillo/ai-agents/issues/7501) tracks the residual work.

## Context

Doc accuracy Phase 3 checks code examples against the repository symbol index.
That index cannot prove that a framework exports a type or member.
The readiness gate needs positive evidence and complete examples.

The first integrated scan at `8f889d682` exited 10 with 801 high findings.
Round 1 of the panel blocked the first draft with six votes.
The owner then chose to repair documents first (D24).
The owner kept the legacy local and stdlib shortcuts (D25).
Phase 3 blocks only the `/build` and `/test` exit gates; pre-PR stays advisory (D26).
The branch fixed reproduced false passes in the current scanner (D27).
D28 narrowly amended D25 to allow occurrence binding and positive member checks.
D29 shipped those changes with this residual tracked.

The replay at `6a8c7e8c8` exited 10 with 1,137 high findings.
All of them are `unresolved_symbol`.
The split is 817 C#, 287 TypeScript, and 33 Python.
They span 111 files, many of them generated mirror copies.
Invented local names shrank after the repairs.
Real framework names grew, led by `System` with 153 findings.
Others include `IReadOnlyDictionary`, `ReadOnlySpan`, and TypeScript `map`.

A probe also showed that shortcuts still accept invented framework names.
These passed without a finding:

- Python `from datetime import UTC, MissingTimezone`
- Python `OrderedDict().invented_member()`
- C# `StringBuilder().Invented()`
- TypeScript `inventedReader` imported from `node:fs`
- TypeScript `Date.Ticks`

## Decision

Prove framework symbols from pinned declarations bound to each occurrence.
Limit this to the .NET BCL, the Python standard library, and TypeScript and Node libraries.
Keep package SDKs as findings unless the document's own lock file pins them.

### Scope

1. Apply declaration proof to occurrences that a legacy shortcut accepts today.
   This covers C-family receivers with a known framework root.
   It covers Python stdlib imports and stdlib alias attribute chains.
2. Prove C# namespace imports such as `using System.Buffers;` from the reference graph.
3. Keep the D25 shortcuts for local types and repository code.
   A follow-up ADR owns their removal.
4. Leave package SDKs such as EF Core, Azure, Stripe, and Prisma out of the bundle.
   Their names stay findings unless a document's own lock file pins the package.

### Proof inputs

1. Resolve one bundle at `~/.project-toolkit/doc-accuracy/<manifest-digest>`.
   The scanner release pins the expected manifest SHA-256.
   Never read a pin, bundle, or manifest from the checkout under review.
   Never search PATH, the target tree, or package caches for proof tools.
   The scanner neither downloads nor changes the bundle.
2. Start with the probed versions.
   Use .NET 10.0.15 reference assemblies with a Roslyn adapter from SDK 10.0.404.
   Use TypeScript 5.9.3 on Node 26.13.1 for declaration queries.
   Use the Python 3.14 typeshed stubs from the locked mypy 2.4.1 distribution.
3. Verify each manifest field and artifact hash before running a tool or reading a declaration.
   Input manifests list tool, package, and file identities only.
   They hold no approved symbols, findings, fence hashes, or prior verdicts.

### Verification

1. Bind each in-scope occurrence to its own declaration.
   A valid occurrence never covers another occurrence with the same spelling.
   Lexical shadowing decides which declaration can bind.
2. Prove a member access through its immediate receiver and declared type.
   Reject missing members, ambiguous bindings, unknown receivers, `any`, and `dynamic`.
3. Run at most one adapter process per language per scan.
   Bound each adapter by time, memory, and output size.
   The scan installs, restores, builds, and executes nothing.

### Gate behavior

1. With a valid bundle, in-scope occurrences need declaration proof.
   An unproven occurrence is a high finding.
2. Without a valid bundle, the scanner keeps the shortcut behavior.
   It reports `proof_unavailable` with the count of occurrences that lacked proof.
3. The `/build` and `/test` exit gates require a valid bundle.
   A missing or invalid bundle there returns exit 1, not a pass.
   This keeps their verdict independent of the host.
4. Pre-PR keeps its advisory prose check. This ADR adds no pre-PR blocker.
5. Exit 10 still means a finding met the threshold.
   Exit 1 still means Phase 3 could not reach a conclusive result.

## Prior Art Investigation

The original scan verifies repository symbols and named parameters.
Commit `f915118ec` added scope and literal handling to reduce false findings.
It kept root-type inference as a fast way to recognize non-repository code.
Commit `3c2a56c1b` added the documented exemption for vendored SDK docs.

The current scanner trusts some framework roots without checking members.
The Python scan blanks attribute chains rooted at stdlib aliases.
It also accepts names from recognized stdlib modules without checking exports.
Round 1 measured 223 added raw findings if they were removed.
D25 kept them.
This ADR leaves them in place and adds proof on top of them.

## Rationale

| Alternative | Benefit | Cost | Decision |
| --- | --- | --- | --- |
| Repair documents alone | Keeps the current toolchain. | Real framework calls still fail against the repo index. | Done first under D24. Not enough alone. |
| Remove the shortcuts now | Ends unproven passes at once. | Round 1 measured 223 added raw findings with no proof source. | Rejected under D25. |
| Index framework member names | Gives fast lookups. | Cannot prove the member on the actual receiver. | Rejected. |
| Search installed SDKs at runtime | Needs less setup. | The same tree can pass on one host and fail on another. | Rejected. |
| Include package SDKs in the bundle | Clears more findings. | Grows the bundle and its refresh duty without a pin source. | Rejected. Lock files can pin them. |
| Pinned framework declarations | Uses the framework as the authority. | Setup must provision and refresh a pinned bundle. | Selected. |

## Consequences

- Real framework references can clear without a hand-kept allowlist.
- The probe's invented framework names become findings where a bundle exists.
- Hosts without a bundle keep today's behavior and see the unproven count.
- `/build` and `/test` fail closed when the bundle is missing.
- Release maintenance must publish and verify bundles for each supported platform.
- Package SDK findings remain until documents pin those packages.

## Impact on Dependent Components

| Component | Change after acceptance |
| --- | --- |
| Six scanner copies | Regenerate the same logic and pins from the canonical Claude source. |
| Hermes delivery pack | Keep proof inputs outside installed packs and within the 399-file budget. |
| Repository setup | Provision the locked bundle before `/build` and `/test` run Phase 3. |
| `/build` Gate 3 and `/test` Gate 5 | Require a valid bundle and surface blocking results. |
| Pre-PR | No change. The prose check stays advisory. |

## Implementation and Acceptance

1. Add .NET BCL, Python stdlib, and TypeScript and Node proof.
2. Turn each probe case above into a failing test before the change.
3. Keep passing tests for real names such as `datetime.UTC` and `StringBuilder.Append`.
4. Test runs with a valid bundle, no bundle, and a mismatched digest.
5. Compare results across all six shipped copies.
6. Replay the full corpus and group remaining findings by cause.
7. Measure Phase 3 wall time and peak RSS beside the `6a8c7e8c8` replay.
   That replay took 12 minutes 56 seconds and 328,940 KiB peak RSS.

## Related Decisions

- [ADR-115](ADR-115-native-plugin-support-per-host.md) describes Hermes pack budgets.
- [ADR-121](ADR-121-one-resolver-for-plugin-root-commands.md) describes plugin launch portability.
- [ADR-122](ADR-122-scoped-parser-dependency-admission.md) covers code-quality parser dependencies.
