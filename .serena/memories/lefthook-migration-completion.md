# Lefthook migration complete

Branch `chore/lefthook-migration` replaced the repository's custom Git hook
engine with pinned Lefthook 2.1.10.

`lefthook.yml` is the scheduler and configuration authority. The former
`.githooks` system, relocated `scripts/hooks` payloads, custom installer,
compatibility wrappers, and SessionStart activation fallback are absent.

The remaining Python boundary, `scripts/validation/git_hook_policy.py`, handles
Git-specific policies that Lefthook does not provide: index blob reads,
alternate indexes, pushed-ref validation, immutable commit security scans,
generated-file allowlist staging, and memory policies.

Active setup and contributor guidance uses standard Lefthook commands. Generated
agent, skill, rule, command, catalog, and hook mirrors ship with the migration.

Validation on 2026-07-19 included 14,093 passing repository tests, 439 targeted
migration tests, 100 percent statement and branch coverage for the policy
module, generated drift checks, pre-PR validation, per-file mypy, Ruff,
Markdown, YAML, workflow, and changed-file Semgrep checks.
