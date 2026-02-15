# Template and Variant Maintenance Architecture

## Statement

Claude variants in `src/claude/*.md` are maintained SEPARATELY from templates in `templates/agents/*.shared.md`. Updates must be applied to BOTH locations.

## Context

When updating agent documentation, naming conventions, or examples.

## Evidence

Session 2025-12-24: User correction when assuming Claude variants were generated from templates. Line 803 in `src/claude/retrospective.md` was missed because only the template was updated.

## Architecture

```
templates/agents/              src/claude/
├── retrospective.shared.md    ├── retrospective.md      ← SEPARATE maintenance
├── orchestrator.shared.md     ├── orchestrator.md       ← SEPARATE maintenance
├── memory.shared.md           ├── memory.md             ← SEPARATE maintenance
└── ...                        └── ...

src/copilot-cli/               src/vs-code-agents/
├── *.agent.md                 ├── *.agent.md
└── (generated from templates) └── (generated from templates)
```

## Key Insight

- `src/claude/*.md` - Manually maintained, NOT generated
- `src/copilot-cli/*.agent.md` - Generated via `build/Generate-Agents.ps1`
- `src/vs-code-agents/*.agent.md` - Generated via `build/Generate-Agents.ps1`
- `templates/agents/*.shared.md` - Source for generated variants only

## Anti-Pattern

Updating only `templates/agents/*.shared.md` and assuming Claude variants will be updated automatically.

## Correct Pattern

1. Update `templates/agents/*.shared.md` (source for copilot-cli and vs-code-agents)
2. Update `src/claude/*.md` (manual, separate maintenance)
3. Run `build/Generate-Agents.ps1` to regenerate copilot-cli and vs-code-agents variants

## Atomicity

95%

## Impact

9/10 - Prevents incomplete documentation updates

## Verification Step (Session 92 Learning)

After running `build/Generate-Agents.ps1`, verify regeneration:

```bash
# Check that copilot-cli variants were regenerated
git diff templates/agents/retrospective.shared.md src/copilot-cli/retrospective.agent.md

# Check that vs-code-agents variants were regenerated
git diff templates/agents/retrospective.shared.md src/vs-code-agents/retrospective.agent.md

# Ensure Claude variants are manually updated
git status src/claude/*.md  # Should show modifications if template changes apply
```

**Expected:** Changes from templates propagate to copilot-cli and vs-code-agents. Claude variants require manual editing.

**Anti-Pattern:** Update template, run generator, commit without verifying diffs.

**Evidence:** Session 92 template-first pattern + architecture-template-variant-maintenance memory

## Related

- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
- [architecture-016-adr-number-check](architecture-016-adr-number-check.md)
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md)
- [architecture-composite-action](architecture-composite-action.md)
