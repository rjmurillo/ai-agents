"""Testable workflow-logic scripts extracted from ai-pr-quality-gate.yml.

Each module here replaces an inline ``run:`` block in the AI PR Quality Gate
workflow (ADR-006: no logic in YAML). Modules expose a ``main(argv)`` entry
point that mirrors the original block's behavior and exit-code contract.
"""
