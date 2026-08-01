---
applyTo: src/claude/**,.claude/agents/**,.claude/skills/**,.claude/commands/**
---

# Claude Agent and Skill Rules

`src/claude/*.md` are hand-maintained Claude agent prompts with unique Claude-specific content (`name`/`model` frontmatter). They are NOT generated. `templates/agents/*.shared.md` holds the shared body that the Copilot and VS Code copies are generated from. **No check compares the content of `src/claude/*.md` against that shared body**; what enforces the lockstep is co-change, not content (see MUST-1). `.claude/agents/`, `.claude/skills/`, and `.claude/commands/` hold per-repo artifacts loaded by Claude Code.

## MUST

1. **Edit Claude agents directly, in lockstep with the shared template**. `src/claude/*.md` is hand-maintained; no generator writes it (`detect_agent_drift.py:19` "Claude agents have unique content and are NOT generated from templates."). To change shared agent behavior, edit BOTH `src/claude/<agent>.md` AND `templates/agents/<agent>.shared.md` in the same change, then run `python3 build/generate_agents.py` to refresh the generated Copilot and VS Code copies (`src/copilot-cli/`, `src/vs-code-agents/`). What enforces the lockstep is `build/scripts/validate_install_parity.py`, and it checks **co-change in a diff, not content agreement**: "reports the sibling files that should have changed together and did not" (`validate_install_parity.py:21`). Nothing compares the two files' text, so a `src/claude/<agent>.md` that silently contradicts its template passes every gate. Read both before you edit either.
2. **Skill schema**. Every skill MUST have a `SKILL.md` with frontmatter fields `name`, `version`, `description` per `.agents/steering/claude-skills.md`.
3. **Skill tests**. New skills MUST include pytest coverage under `.claude/skills/<name>/tests/`.
4. **File cap per PR**. Skill additions SHOULD ship ≤10 files per PR (see `.agents/steering/claude-skills.md`).
5. **No internal references in `src/claude/`**. Files under `src/claude/` MUST NOT reference `.agents/` paths that will not exist for downstream installers.
6. **Python for skill scripts**. New skill scripts MUST be Python per ADR-042.
7. **Test what the prose promises**. When a `SKILL.md` names a script, an exit code, and what that code means, it has defined an executable contract, and at least one file under `tests/` MUST assert the documented exit-code behavior. Prose is not enforcement: a documented exit code that nothing asserts drifts from the script the first time someone edits the script and not the document, and the drift is invisible because the document still reads correctly. `check_skill_contract_tests.py` enforces this.

## SHOULD

1. **One skill, one purpose**. Skills SHOULD do one thing well. Split multi-purpose skills.
2. **Idempotent tools**. Skills that mutate state SHOULD be safe to re-run (or detect prior completion).
3. **Invoke via the Skill tool**. Claude Code agents SHOULD invoke matching skills via the `Skill` tool, not inline equivalents.

## MUST NOT

1. MUST NOT hand-edit generated agent files (`src/copilot-cli/`, `src/vs-code-agents/`) to add behavior; add it to the template and regenerate. This does NOT apply to `src/claude/*.md`, which is hand-maintained and edited directly.
2. MUST NOT bundle skill code changes with memory changes in the same PR (separate concerns).

## What the drift detector does and does not catch

A green `build/scripts/detect_agent_drift.py` is not proof that two agent copies agree. Read its scope before you rely on it.

It compares two pairs, and `templates/` is in neither:

1. `src/claude/*.md` against `src/vs-code-agents/*.agent.md`
2. `.claude/agents/*.md` against `.github/agents/*.agent.md`

`templates/agents/*.shared.md` is read for FILENAMES only, to pick which agents take part in comparison 2 (`shared_template_names`, `detect_agent_drift.py:536-544`, `frozenset(p.name.removesuffix(".shared.md") for p in templates_path.glob("*.shared.md"))`). The template body is never a comparison input.

Within a pair it scores only the sections named in `SECTIONS_TO_COMPARE` (`detect_agent_drift.py:57`), an 18-entry allowlist. Everything outside it is invisible, including a whole section present in one copy and absent from the other.

Measured on `origin/main` at `7e8d3ac2f4` (2026-08-01): across the 32 files in `src/claude/*.md`, the 18 allowlisted sections hold 48,177 of the 426,714 characters that `get_markdown_sections()` returns, 11.3%. 8 of 60 comparisons match zero sections and return a hardcoded 100.0 via `detect_agent_drift.py:302` (`overall = round(total_similarity / compared_count, 1) if compared_count > 0 else 100.0`). Those are the two comparisons each for `analyst`, `explainer`, `silent-failure-hunter`, and `type-design-analyzer`: for those four agents the gate cannot fail. Replacing the entire body of `src/vs-code-agents/silent-failure-hunter.agent.md` with one unrelated sentence still yields RC=0 / 100.0 / OK; the identical mutation on `architect` (10 compared sections) yields RC=1 / 0.0 / DRIFT DETECTED.

This is the tool working as documented (`detect_agent_drift.py:29-33` names the sections it focuses on), not a defect. The error to avoid is reading its silence as parity.

## References

- `build/generate_agents.py`. Generator (emits the Copilot and VS Code copies `src/copilot-cli/`, `src/vs-code-agents/` only; does NOT write `src/claude/`)
- `build/scripts/detect_agent_drift.py`. Semantic-similarity check on two OTHER pairs (`src/claude` vs `src/vs-code-agents`; `.claude/agents` vs `.github/agents`). Does NOT read `templates/agents/*.shared.md` content.
- `build/scripts/validate_install_parity.py`. Enforces that the sibling copies move together in a diff (co-change, not content)
- `.agents/steering/agent-prompts.md`. Prompt standards
- `.agents/steering/claude-skills.md`. Skill authoring standards
- `scripts/validation/check_skill_contract_tests.py`. Enforces the executable-contract test requirement
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- Issue #3402. worktree identity and stale helper resolution
