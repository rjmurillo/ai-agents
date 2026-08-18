---
applyTo: '**'
---

# Universal Rules

These rules apply to every change in this repository.

## MUST

1. **Branch discipline**. MUST NOT push or commit directly to `main` or `master`. Create a feature branch first.
2. **Issue linkage**. Every PR MUST reference an issue with `Fixes #<n>` or `Refs #<n>` in the description.
3. **Verify closing keywords against the diff before merging.** `Fixes #<n>` closes on merge; tie each claim to a named hunk. Downgrade unsupported claims to `Refs #<n>` with reason. Missing closing keywords are not automatically defects. Agent-authored PR bodies SHOULD use `These references do not close their linked items:` for bare `Refs`. Read the body before adding a closing keyword to another author's PR. Post-merge body edits are inert; close orphaned issues with a comment citing the merge commit. Evidence: on 2026-08-03, 15 claimed closing keywords across five PRs were unsupported, and four of seven keyword-free PRs repaired from title matches explicitly should not close the issue.
4. **Verify a red remote check with equivalent evidence, or report it unreproduced.** MUST NOT claim a red remote check is cleared by a local run unless the checker, ruleset, flags, and version are demonstrably identical. State the command and why it is the same check; if you cannot, say the check is red and you could not reproduce it. A different tool produces evidence about a different check, and calling that "resolved" tells the reader to disregard a live finding.
5. **Conventional commits**. Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.
6. **Atomic commits**. Each commit MUST touch five or fewer authored files (see `AGENTS.md` boundaries). Hook-generated companions (session episodes, MCP config, agent catalog, memory index) are exempt and do not count toward the limit.
7. **No secrets**. MUST NOT commit credentials, tokens, or API keys. Secrets live in environment variables or the secrets manager.
8. **Pin Actions to SHA**. New GitHub Actions references MUST pin to a commit SHA, never a floating tag.
9. **Session continuity**. Long-running issue work MUST preserve continuity in
   the per-issue handoff and Serena memory. Session logs are optional and
   validate only when staged or explicitly supplied.
10. **Git identity cannot prove a human acted.**

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
   disables selected jobs. All six are forbidden. Naming only
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
7. Git worktrees MUST be external.

## References

- `AGENTS.md`. Boundaries and standards
- `.agents/governance/PROJECT-CONSTRAINTS.md`. Canonical constraints
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- `.agents/SESSION-PROTOCOL.md`. Session gates
