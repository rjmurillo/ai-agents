---
number: 181
title: "feat: Add CLI Init Command for Project Scaffolding"
state: OPEN
created_at: 12/20/2025 11:14:16
author: rjmurillo-bot
labels: ["enhancement", "priority:P2"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/181
---

# feat: Add CLI Init Command for Project Scaffolding

## Summary

Implement an init command that scaffolds the agent system configuration for new projects.

## Background

Claude-flow's init command creates CLAUDE.md, .claude/ directory structure, memory directories, coordination directories, and updates .gitignore. It supports options like --minimal, --sparc, and --force.

## Current State

- Manual installation via PowerShell scripts
- No single-command project setup
- No configuration scaffolding
- Templates must be copied manually

## Proposed Solution

1. **Init Command**:
   ```bash
   npx ai-agents init
   npx ai-agents init --minimal
   npx ai-agents init --force
   ```
   
2. **Generated Structure**:
   - `.agents/` directory with subdirectories
   - `CLAUDE.md` with project configuration
   - `.github/copilot-instructions.md`
   - Memory and session directories
   - .gitignore updates
   
3. **Configuration Options**:
   - `--minimal`: Basic setup only
   - `--force`: Overwrite existing files
   - `--dry-run`: Preview changes
   - `--platform`: Target platform (claude, vscode, all)
   
4. **CLAUDE.md Templates**:
   - Full template with all features
   - Minimal template for simple projects
   - Custom template support

## Benefits

- Single-command project setup
- Consistent configuration across projects
- Lower barrier to adoption
- Version-controlled templates

## Implementation Notes

- Implement as npm package or PowerShell module
- Detect existing configuration
- Support template customization
- Add verification step

## Reference

See claude-flow's Init Command Architecture (wiki page 11.1).

## Analysis Document

`.agents/analysis/claude-flow-architecture-analysis.md`

---

## Comments

### Comment by @coderabbitai on 12/20/2025 11:15:43

<!-- This is an auto-generated issue plan by CodeRabbit -->


### 📝 CodeRabbit Plan Mode
Generate an implementation plan and prompts that you can use with your favorite coding agent.

- [ ] <!-- {"checkboxId": "8d4f2b9c-3e1a-4f7c-a9b2-d5e8f1c4a7b9"} --> Create Plan

<details>
<summary>Examples</summary>

- [Example 1](https://github.com/coderabbitai/git-worktree-runner/issues/29#issuecomment-3589134556)
- [Example 2](https://github.com/coderabbitai/git-worktree-runner/issues/12#issuecomment-3606665167)

</details>

---

<details>
<summary><b>🔗 Similar Issues</b></summary>

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/124
- https://github.com/rjmurillo/ai-agents/issues/170
- https://github.com/rjmurillo/ai-agents/issues/168
- https://github.com/rjmurillo/ai-agents/issues/57
- https://github.com/rjmurillo/ai-agents/issues/8
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/vs-code-agents#11 - feat: achieve Claude agent parity with VS Code agents [merged]
rjmurillo/vs-code-agents#13 - docs: update documentation to reflect agent parity [merged]
rjmurillo/ai-agents#43 - feat: add shared template system for multi-platform agent generation [merged]
rjmurillo/ai-agents#54 - docs(agents): Add comprehensive agent system documentation and planning scaffolds [merged]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo](https://github.com/rjmurillo)
- [rjmurillo-bot](https://github.com/rjmurillo-bot)
</details>


---
<details>
<summary> 🧪 Issue enrichment is currently in open beta.</summary>


You can configure auto-planning by selecting labels in the issue_enrichment configuration.

To disable automatic issue enrichment, add the following to your `.coderabbit.yaml`:
```yaml
issue_enrichment:
  auto_enrich:
    enabled: false
```
</details>

💬 Have feedback or questions? Drop into our [discord](https://discord.gg/coderabbit) or [schedule a call](https://calendly.com/parth-coderabbit/issues-feedback)!

