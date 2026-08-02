---
applyTo: '**'
---

# Universal Rules

These rules apply to every change in this repository.

## MUST

1. **Branch discipline**. MUST NOT push or commit directly to `main` or `master`. Create a feature branch first.
2. **Issue linkage**. Every PR MUST reference an issue with `Fixes #<n>` or `Refs #<n>` in the description.
3. **Conventional commits**. Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.
4. **Atomic commits**. Each commit MUST touch five or fewer authored files (see `AGENTS.md` boundaries). Hook-generated companions (session episodes, MCP config, agent catalog, memory index) are exempt and do not count toward the limit.
5. **No secrets**. MUST NOT commit credentials, tokens, or API keys. Secrets live in environment variables or the secrets manager.
6. **Pin Actions to SHA**. New GitHub Actions references MUST pin to a commit SHA, never a floating tag.
7. **Session log**. Long-running work MUST have a session log under `.agents/sessions/` per `.agents/SESSION-PROTOCOL.md`. Two mechanics are enforced and are not obvious from the protocol document:
   - A commit that stages anything under `.agents/**` MUST carry a session log named `.agents/sessions/YYYY-MM-DD-session-NN<slug>.json` **in that same commit**. `scripts/validation/git_hook_policy.py session` rejects the commit with `ERROR: staged .agents changes require a JSON session log` otherwise, and it runs on every `.agents/**` path, not only on long-running work. Writing the log afterwards does not clear it; the log and the change must land together.
   - `endingCommit` MUST be recorded in a **follow-up commit, never by amending**. Amending replaces the commit whose SHA the log names, so `validate_session_json.py` then reports the recorded SHA as unreachable (issue #3618). Commit the work with `endingCommit` empty, which is only a warning, then commit the SHA.

## SHOULD

1. **Retrieval-led reasoning**. SHOULD read `.agents/governance/PROJECT-CONSTRAINTS.md` and `.agents/architecture/ADR-*.md` before acting, not rely on pre-training.
2. **Skill-first**. SHOULD prefer an existing skill (`.claude/skills/<name>`) over inline `gh`, `git`, or shell scripting when a skill exists.
3. **Python for new scripts**. SHOULD use Python per ADR-042. MUST NOT create new bash scripts.
4. **Minimal diff**. SHOULD NOT introduce unrelated refactors in a change. Keep the blast radius small.

## MUST NOT

1. MUST NOT force-push shared branches.
2. MUST NOT skip hooks or bypass signing. ADR-086 lines 95 to 98 enumerate five
   local bypasses and state that policy forbids using them to skip required
   checks: `git --no-verify`, `LEFTHOOK=0`, an overridden `LEFTHOOK_BIN`, a
   lefthook configuration override, and a direct edit to an installed hook.
   This rule adds a sixth the ADR does not name, `LEFTHOOK_EXCLUDE`, which
   disables selected jobs rather than the whole run. Policy forbids all six
   equally. Naming only
   `--no-verify` invites the reading that a different mechanism is sanctioned;
   it is not, and no repository document describes any of them as a supported
   skip. Protected CI is a backstop, not a substitute: a bypassed push shifts
   a 10 minute local failure into a slower remote one and can leave the branch
   red for other agents. When a hook blocks you for a reason unrelated to your
   diff, hand the branch back with the measurement instead of bypassing.
3. MUST NOT edit `.agents/HANDOFF.md` (read-only per ADR-014).
4. MUST NOT put logic in YAML workflows (ADR-006).
5. MUST NOT use em-dashes (U+2014) or en-dashes (U+2013) in any authored text:
   markdown prose, code comments, agent prompts, commit messages, PR descriptions,
   rule files (`.claude/rules/`, `.github/instructions/`), retrospectives, ADRs,
   or session logs. Use commas, periods, colons, parentheses, hyphens, or
   restructure the sentence. Bot reviewers (Copilot, CodeRabbit) flag every
   occurrence; the cost is one or more threads per dash, every PR. The rule binds
   identically to the Copilot-side mirror at
   `.github/instructions/universal.instructions.md`; do not regress one tree
   while fixing the other. **Carve-out**: test fixtures under
   `tests/hooks/fixtures/` are exempt because they intentionally carry the
   prohibited bytes to exercise detection logic; the dash-guard hook and the
   `validate_dash_prohibition` validator both skip that prefix. Refs Issue #1923.
6. MUST NOT add auto-generated headers, generation timestamps, or "do not edit"
   comments to any file (agent prompts, documentation, code, template outputs).
   Generated output must be indistinguishable from hand-written content:
   metadata headers waste tokens for AI consumers, and the user has rejected
   this pattern repeatedly (three corrections as of 2025-12-17). If a script
   grows a helper that emits such headers, delete the helper instead of
   calling it.

## References

- `AGENTS.md`. Boundaries and standards
- `.agents/governance/PROJECT-CONSTRAINTS.md`. Canonical constraints
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- `.agents/SESSION-PROTOCOL.md`. Session gates
