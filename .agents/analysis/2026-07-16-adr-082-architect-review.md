---
status: recorded
reviewer: architect agent (session 3044)
verdict: APPROVE-WITH-CHANGES
---

# Architect Review: ADR-082 (Claude-side consolidated hook group dispatch)

Architect-agent gate review of the ADR-082 decision and implementation on
branch `perf/claude-hook-dispatch`, recorded verbatim in substance from the
agent's verdict (2026-07-16, session 3044). This artifact satisfies the
adr-architect-gate evidence requirement; the full multi-agent adr-review
debate runs on the PR.

## Verdict

APPROVE-WITH-CHANGES. Design sound, properly extends ADR-068, merge rules
protocol-safe, self-host bail not a security hole. Conditions and findings
below.

## Findings and resolutions

1. BLOCKER: ADR-082 must exist on disk, cite ADR-068 as parent, explain why
   the safe-multiplexer bar from the 2026-07-14 analysis (which rejected a
   Claude-side dispatcher) is now met, and state distribution context.
   RESOLVED: `.agents/architecture/ADR-082-claude-hook-group-dispatch.md`
   authored in the same change.
2. P1: no test asserted the self-host coverage invariant (plugin shims minus
   repo-settings shims equals the documented prune allowlist). A plugin
   guard added without a settings entry would silently never run in this
   repo (silent dead-hook class).
   RESOLVED: `tests/hooks/test_dispatch_groups_parity.py::`
   `test_repo_settings_cover_plugin_shims_minus_documented_prunes`.
3. P2 (documented in ADR consequences): per-shim timeout isolation lost
   (host enforces group budget only); in-process runpy shares module and
   environ state across sibling shims; the self-host bail keys on plugin
   name equality; `suppressOutput`/`systemMessage` fields on a context-only
   document are dropped during merge; a gate_all shim that blocks AND emits
   a decision document has the document logged, not merged.
4. P2: the plugin still ships `invoke_session_start_memory_first.py`, so
   consumers keep the ADR-007 double-emit; only the publishing repo prunes
   it. Named in ADR consequences; consumer-side prune deferred to its own
   change so plugin membership stays untouched here.

## Failure mode named for the two-year horizon

Silent guard-drop, in two shapes: a plugin guard without a settings
counterpart vanishing under the self-host bail (closed by the P1 test), and
the name-keyed bail suppressing plugin hooks for a fork with divergent
settings (documented ADR consequence).
