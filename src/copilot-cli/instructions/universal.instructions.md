---
applyTo: '**'
---

# Universal Rules

These rules apply to every change in this repository.

## MUST

1. **Branch discipline**. MUST NOT push or commit directly to `main` or `master`. Create a feature branch first.
2. **Issue linkage**. Every PR MUST reference an issue with `Fixes #<n>` or `Refs #<n>` in the description.
3. **Verify every closing keyword against the diff before merging.** `Fixes #<n>` is an instruction to GitHub, not a note to the reader: merging executes it and closes the issue whether or not the diff does the work. Before merging, read each issue the PR claims to close and confirm the diff actually closes it. Downgrade every unsupported claim to `Refs #<n>` and say why in the body. Measured on 2026-08-03 across five open PRs: 15 of the closing keywords present did not survive that check. One PR claimed `Fixes` on ten issues of which five were unsupported, including two that were already closed and one whose fix lived in a different PR's diff; another PR's three claims all failed and it merged with zero. The failure is silent and it inverts the signal, because the backlog looks smaller exactly when it has become less accurate, and a falsely closed issue is harder to find again than an open one. A claim is supported only when you can name the hunk that does the work.
4. **Conventional commits**. Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.
5. **Atomic commits**. Each commit MUST touch five or fewer authored files (see `AGENTS.md` boundaries). Hook-generated companions (session episodes, MCP config, agent catalog, memory index) are exempt and do not count toward the limit.
6. **No secrets**. MUST NOT commit credentials, tokens, or API keys. Secrets live in environment variables or the secrets manager.
7. **Pin Actions to SHA**. New GitHub Actions references MUST pin to a commit SHA, never a floating tag.
8. **Session log**. Long-running work MUST have a session log under `.agents/sessions/` per `.agents/SESSION-PROTOCOL.md`.

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
   **Quotations**: the ban still applies inside external quotes. If a quoted
   span or title has a prohibited dash, do not rewrite it. End the quote before
   it, use `[...]`, or split the quote and explain the dash's job in your prose.
   Refs Issue #4079.
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
