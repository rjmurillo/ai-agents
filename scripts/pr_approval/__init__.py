"""Observe-mode PR approval policy evaluator.

Evaluates a read-only PR evidence snapshot against
``.github/pr-approval-policy.toml`` and records an advisory decision. It holds
no credentials, makes no network calls, posts nothing, approves nothing, and
merges nothing. See ``.project-toolkit/specs/SPEC-policy-driven-pr-approvals.md``.
"""
