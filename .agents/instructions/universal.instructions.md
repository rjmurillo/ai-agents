---
applyTo: "**"
priority: critical
---

# Universal Rules

These rules apply to every change in this repository.

## MUST

1. **Branch discipline** — MUST NOT push or commit directly to `main` or `master`. Create a feature branch first.
2. **Issue linkage** — Every PR MUST reference an issue with `Fixes #<n>` or `Refs #<n>` in the description.
3. **Conventional commits** — Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.
4. **Atomic commits** — Each commit MUST touch five or fewer files (see `AGENTS.md` boundaries).
5. **No secrets** — MUST NOT commit credentials, tokens, or API keys. Secrets live in environment variables or the secrets manager.
6. **Pin Actions to SHA** — New GitHub Actions references MUST pin to a commit SHA, never a floating tag.
7. **Session log** — Long-running work MUST have a session log under `.agents/sessions/` per `.agents/SESSION-PROTOCOL.md`.

## SHOULD

1. **Retrieval-led reasoning** — SHOULD read `.agents/governance/PROJECT-CONSTRAINTS.md` and `.agents/architecture/ADR-*.md` before acting, not rely on pre-training.
2. **Skill-first** — SHOULD prefer an existing skill (`.claude/skills/<name>`) over inline `gh`, `git`, or shell scripting when a skill exists.
3. **Python for new scripts** — SHOULD use Python per ADR-042. MUST NOT create new bash scripts.
4. **Minimal diff** — SHOULD NOT introduce unrelated refactors in a change. Keep the blast radius small.

## MUST NOT

1. MUST NOT force-push shared branches.
2. MUST NOT skip hooks (`--no-verify`) or bypass signing.
3. MUST NOT edit `.agents/HANDOFF.md` (read-only per ADR-014).
4. MUST NOT put logic in YAML workflows (ADR-006).

## References

- `AGENTS.md` — boundaries and standards
- `.agents/governance/PROJECT-CONSTRAINTS.md` — canonical constraints
- `.agents/architecture/ADR-042-python-migration-strategy.md` — Python-first
- `.agents/SESSION-PROTOCOL.md` — session gates
