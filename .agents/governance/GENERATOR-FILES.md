# Generator-Owned Files

This inventory lists every file tree that the build pipeline generates from a
canonical source. Editing a generated file directly is wasted work: the next
`build_all.py` run overwrites it, and the drift check (`build_all.py --check`)
fails the PR. Edit the source, then regenerate.

If you are about to edit a file under any "Output" path below, stop and edit the
matching "Source" instead.

## Generated trees

| Generator | Source (edit here) | Output (do not edit) | Spec |
|-----------|--------------------|----------------------|------|
| `build/generate_agents.py` | `templates/agents/*.shared.md` | `src/claude/`, `src/copilot-cli/agents/`, `src/vs-code-agents/` (per platform YAML) | ADR-002 |
| `build/scripts/generate_rules.py` | `.claude/rules/*.md` | `.github/instructions/*.instructions.md`, `src/copilot-cli/instructions/*.instructions.md` | REQ-003-006 |
| `build/scripts/generate_skills.py` | `.claude/skills/<name>/` | `src/copilot-cli/skills/<name>/` | REQ-003-001 |
| `build/scripts/generate_commands.py` | `.claude/commands/<name>.md` | `src/copilot-cli/skills/<name>/SKILL.md` | REQ-003-001 |
| `build/scripts/generate_hooks.py` | `.claude/hooks/` + `.claude/settings.json` | `src/copilot-cli/hooks/` + `src/copilot-cli/hooks/hooks.json` | REQ-003-007 |
| `build/scripts/generate_pr_quality_prompts.py` | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | REQ-008-01 |

## Hand-maintained sibling copies (NOT generated)

These trees are NOT written by any generator. REQ-003-010 forbids generators from
writing under `.claude/`. They are kept in sync by hand and guarded by the
install-parity validator, which fails CI when a sibling drifts from its source.

| Path | Role | Guard |
|------|------|-------|
| `.claude/agents/<name>.md` | Claude Code self-host agent copy | `build/scripts/validate_install_parity.py` |
| `.github/agents/<name>.agent.md` | GitHub Copilot self-host agent copy | `build/scripts/validate_install_parity.py` |

## Regenerating

`build/scripts/build_all.py` orchestrates the generators (skills, agents,
commands, rules, hooks):

```bash
# Regenerate everything from canonical sources.
python3 build/scripts/build_all.py

# Verify generated trees match sources without writing (CI drift gate).
python3 build/scripts/build_all.py --check

# Agents only (also runnable standalone).
python3 build/generate_agents.py

# PR-quality CI prompts only.
python3 build/scripts/generate_pr_quality_prompts.py
```

After editing a source listed above, run the matching regen command and commit
the regenerated output in the same PR. A plugin source change also requires a
`plugin.json` version bump (see AGENTS.md, Issue #2118).

## References

- ADR-002: agent model selection and platform emission.
- `templates/README.md`: template structure.
- `build/scripts/validate_install_parity.py`: hand-maintained sibling guard.
- `.claude/rules/canonical-source-mirror.md`: claims of parity must cite and
  quote the canonical source.
- Issue #1921: this inventory.
