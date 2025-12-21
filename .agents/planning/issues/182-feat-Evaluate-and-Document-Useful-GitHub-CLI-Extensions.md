---
number: 182
title: "feat: Evaluate and Document Useful GitHub CLI Extensions"
state: OPEN
created_at: 12/20/2025 11:14:41
author: rjmurillo-bot
labels: ["documentation", "enhancement", "area-workflows", "priority:P2"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/182
---

# feat: Evaluate and Document Useful GitHub CLI Extensions

## Summary

Evaluate and document useful GitHub CLI (`gh`) extensions that could enhance our AI agent workflows, particularly for issue management, PR operations, release management, and org-wide reporting.

## Background

The `gh` CLI supports a rich extension ecosystem. Many community extensions provide capabilities beyond built-in commands. These could complement our existing GitHub skill scripts.

## Extension Categories to Evaluate

### Productivity & Workflow
- **`dash`** – Dashboard for PRs + issues with filters/UI
- **`combine-prs`** – Merge multiple PRs into one
- **`projects`** – Official projects management extension
- **`pulls`** – List your PRs across repos
- **`label`** / **`milestone`** – Manage labels/milestones via CLI
- **`actions-status`** – See actions health across an org

### Repo/File Operations
- **`cp`** – Copy files from a GitHub repo without cloning
- **`download`** – Download folders/files via CLI
- **`repo-explore`** – Interactively browse a repo
- **`clone-org`** – Clone all repos from an org

### Dev / Git Helpers
- **`workon`** – Create branch + assign to you based on an issue
- **`clean-branches`** / **`poi`** – Cleanup local branches
- **`subrepo`** – Submodule manager
- **`describe`** – `git describe`-style tags in shallow repos

### Metrics / Insights
- **`metrics`** – Basic PR/issue metrics summary
- **`collab-scanner`** – View collaboration info
- **`sql`** – Run SQL queries against GitHub Projects (beta)

### Release / Versioning
- **`semver`** – Calculate next semantic version for releases
- **`changelog`** / **`gh-changelog`** – Generate changelogs

## Evaluation Criteria

1. **Workflow Fit**: Does it complement our existing GitHub skill scripts?
2. **Maintenance**: Is the extension actively maintained?
3. **Agent Compatibility**: Can it be invoked programmatically by agents?
4. **Value Add**: Does it reduce manual steps or enable new capabilities?

## Proposed Actions

1. Install and test promising extensions locally
2. Document extensions that pass evaluation in `.claude/skills/github/EXTENSIONS.md`
3. Add wrapper scripts to GitHub skill for agent-friendly invocation
4. Consider contributing improvements upstream

## Discovery Commands

```bash
# Browse extensions interactively
gh extension browse

# Search by keyword
gh extension search <keyword>

# Install an extension
gh extension install owner/gh-extension-name

# List installed extensions
gh extension list
```

## References

- [Awesome gh-cli extensions](https://github.com/kodepandai/awesome-gh-cli-extensions)
- [GitHub Blog: New GitHub CLI extension tools](https://github.blog/developer-skills/github/new-github-cli-extension-tools/)

---

## Comments

### Comment by @coderabbitai on 12/20/2025 11:15:47

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
- https://github.com/rjmurillo/ai-agents/issues/57
- https://github.com/rjmurillo/ai-agents/issues/179
- https://github.com/rjmurillo/ai-agents/issues/97
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/ai-agents#100 - fix(ci): ensure Pester Tests workflow satisfies required checks for all PRs [merged]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo-bot](https://github.com/rjmurillo-bot)
- [rjmurillo](https://github.com/rjmurillo)
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

