# ADR-008 / ADR-066 Reconciliation (2026-06-11)

ADR-066 (hook fail-open reconciliation) replaces ADR-008's fail-open runtime
contract for hooks: prevention-first, fail-closed-and-loud. ADR-008's text was
amended 2026-06-11 to defer to ADR-066 (failure-semantics bullets and the
"Fail-open" design principle). ADR-008's lifecycle-hook decision itself is
still binding.

Why it matters: until the amendment, the tree asserted both contracts, and a
reviewer cited the superseded ADR-008 text against ADR-066-compliant changes
on PR #2556, burning a review cycle.

When reviewing hook failure semantics, cite ADR-071 (Accepted) Decision
item 5 as the binding rule (hooks MUST fail closed and loud, never silently
degrade) and ADR-066 D1 (policy detail) and D2 (exit-code table) for the
reconciliation specifics. ADR-066 is the detailed reconciliation doc; ADR-071
item 5 is the accepted authority. The Stop host ignores exit codes; per D2 the repository
still treats a failed Stop hook as failed and relies on pre-push, CI, and
runtime-contract tests.

Refs: .agents/architecture/ADR-066-hook-fail-open-reconciliation.md, #2271,
#2205, PR #2556.
