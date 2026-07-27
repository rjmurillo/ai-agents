# Hook Runtime: Split Rationale and Dispatcher Origin

The WHY behind the Phase 3 hook-runtime tables. SKILL.md keeps the two operative tables (registration split, failure policy per family) so you can act; this reference carries the rationale and the dispatcher's version history, which you consult when you need to justify or change the policy. Harness-level exit and timeout details are owned by `agent-harness-reference`.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

## Why failure policy is per family, not global

Guards that assert an invariant on shipped artifacts must fail loud. A silent exit 0 disabled a hook for 33 days in #2205. Observer and lifecycle behavior follows the host event contract instead of a repository-wide exit policy. Older ADRs (008, 033, 035) still carry blanket fail-open language; ADR-066 and ADR-071 own the released-artifact direction. SessionStart hooks cannot block regardless.

## Why one dispatcher per event (ADR-068)

The dispatcher originated in Copilot CLI 1.0.57-era matcher and timeout behavior. Copilot CLI 1.0.72-1 honors supported matchers and fails open on timeout, but one dispatcher per event remains the compatibility fallback and single-producer boundary for PermissionRequest translation. Harness details are owned by `agent-harness-reference`. Issue #3218 owns removal or simplification of the transitional dispatcher.
