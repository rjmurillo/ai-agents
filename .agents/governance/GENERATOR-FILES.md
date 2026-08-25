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
| `build/generate_agents.py` | `templates/agents/*.shared.md` | `src/copilot-cli/agents/`, `src/vs-code-agents/` (per platform YAML) | ADR-002 |
| `build/scripts/generate_rules.py` | `.claude/rules/*.md` | `.github/instructions/*.instructions.md`, `src/copilot-cli/instructions/*.instructions.md` | REQ-003-006 |
| `build/scripts/generate_skills.py` | `.claude/skills/<name>/` | `src/copilot-cli/skills/<name>/` | REQ-003-001 |
| `build/scripts/generate_commands.py` | `.claude/commands/<name>.md` | `src/copilot-cli/skills/<name>/SKILL.md` | REQ-003-001 |
| `build/scripts/generate_hooks.py` with `build/scripts/generate_dispatcher.py` | `.claude/hooks/` + `.claude/settings.json` | `src/copilot-cli/hooks/` + `src/copilot-cli/hooks/hooks.json` | REQ-003-007, ADR-068 |
| `build/scripts/build_all.py` (`_build_lib`) | `.claude/lib/` | `src/copilot-cli/lib/` | REQ-003-001, REQ-003-002 |
| `build/scripts/generate_pr_quality_prompts.py` | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | REQ-008-01 |
| `build/scripts/generate_adr_index.py` (via `build_all.py`'s `_build_adr_index`) | `.agents/architecture/ADR-*.md` (lifecycle status, date, successor from frontmatter; title, decision summary, blocker from body prose) | `.agents/architecture/README.md` | issue #5198 |

## Hand-maintained sibling copies (NOT generated)

These trees are NOT written by any generator. REQ-003-010 forbids generators from
writing under `.claude/`. They are kept in sync by hand and guarded by the
install-parity validator, which fails CI when a sibling drifts from its source.

| Path | Role | Guard |
|------|------|-------|
| `.claude/agents/<name>.md` | Claude Code self-host agent copy | `build/scripts/validate_install_parity.py` |
| `.github/agents/<name>.agent.md` | GitHub Copilot self-host agent copy | `build/scripts/validate_install_parity.py` |
| `src/claude/<name>.md` | claude-agents plugin agent copy | `build/scripts/validate_install_parity.py` |

`src/claude/` is a hand-maintained copy, not a generator output. It was
misclassified as a strict vendored copy until Issue #2882; the membership rule
in `validate_install_parity.py` (`_SHARED_AGENT_HAND_MAINTAINED_PREFIXES`) is
the authority. Editing a shared agent means editing the template plus all three
copies in this table; running `build_all.py` will not do it for you.

## Regenerating

`build/scripts/build_all.py` orchestrates the generators (skills, agents,
commands, rules, hooks):

```bash
# Regenerate everything from canonical sources.
uv run python build/scripts/build_all.py

# Verify generated trees match sources without writing (CI drift gate).
uv run python build/scripts/build_all.py --check

# Agents only (also runnable standalone).
uv run python build/generate_agents.py

# PR-quality CI prompts only.
python3 build/scripts/generate_pr_quality_prompts.py
```

After editing a source listed above, run the matching regen command and commit
the regenerated output in the same PR. A plugin source change requires no
`plugin.json` edit: the manifests carry no `version` field, and adding one back
fails `build/scripts/validate_plugin_version_bump.py` (ADR-092, Issue #4080).

The Copilot hook generator retains per-matcher shim wrappers, then emits one
dispatcher registration per event when the platform enables dispatcher mode.
`build/scripts/generate_hooks_events.py` owns publication and cleanup:
dispatcher artifacts, stale generated matcher shims, and ownership-proven
orphan-event files are changed through `HookGenerationTransaction`. Unknown,
unsafe, and NO-REGEN files are preserved. Only empty orphan directories are
removed after the transaction commits.

## References

- ADR-002: agent model selection and platform emission.
- `templates/README.md`: template structure.
- `build/scripts/validate_install_parity.py`: hand-maintained sibling guard.
- `.claude/rules/canonical-source-mirror.md`: claims of parity must cite and
  quote the canonical source.
- Issue #1921: this inventory.
