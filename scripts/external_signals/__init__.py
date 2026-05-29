"""Externally-grounded gate signals.

Helpers in this package produce deterministic, non-LLM verdicts that quality
gates can use as the sole basis for blocking a merge. LLM judgments may
*enrich* the reports these tools emit, but per issue #1855 must never be the
only signal that decides whether ``ai-pr-quality-gate.yml`` or
``ai-spec-validation.yml`` passes.

See ``docs/design/external-signal-gating.md`` for the contract that the
workflow wiring (tracked separately) must honor.
"""
