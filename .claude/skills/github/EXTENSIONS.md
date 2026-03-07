# GitHub CLI Extensions

Evaluated extensions for AI agent workflows. Extensions below passed evaluation criteria and provide value beyond built-in `gh` commands.

---

## Currently Installed

| Extension | Purpose | Agent Compatible | Maintenance |
|-----------|---------|------------------|-------------|
| `gh-act` | Run GitHub Actions locally | Yes | Active (nektos) |
| `gh-combine-prs` | Merge multiple PRs | Yes | Active (rnorth) |
| `gh-copilot` | GitHub Copilot CLI integration | Yes | Active (github) |
| `gh-gr` | Git repo management | Yes | Active (sarumaj) |
| `gh-grep` | Search across repositories | Yes | Active (k1LoW) |
| `gh-hook` | Webhook testing | Yes | Active (lucasmelin) |
| `gh-metrics` | Repository metrics | Yes | Active (hectcastro) |
| `gh-milestone` | Milestone management | Yes | Active (valeriobelli) |
| `gh-notify` | Notification dashboard | Limited | Active (meiji163) |
| `gh-sub-issue` | Sub-issue management | Yes | Active (yahsan2) |

---

## Recommended Extensions

### High Priority

Extensions that provide significant workflow value and are agent-friendly.

#### `gh-dash` (dlvhdr/gh-dash)

**Purpose**: Rich terminal dashboard for PRs and issues with filters.

**Workflow Fit**: Complements our GitHub skill scripts by providing visual overview.

**Agent Compatibility**: Limited. Interactive TUI, not ideal for programmatic use.

**Value Add**: Developer experience for manual review, not for automation.

**Installation**:

```bash
gh extension install dlvhdr/gh-dash
```

**Usage**:

```bash
# Launch interactive dashboard
gh dash

# Filter PRs
gh dash --filter "is:pr is:open"
```

**Recommendation**: Install for manual use. Do NOT use in agent workflows. Use `Get-PullRequests.ps1` instead.

---

#### `gh-projects` (github/gh-projects)

**Purpose**: Official GitHub Projects (V2) management.

**Workflow Fit**: Enables project board automation for roadmap planning.

**Agent Compatibility**: Yes. CLI interface with JSON output.

**Value Add**: Projects API access without custom GraphQL.

**Installation**:

```bash
gh extension install github/gh-projects
```

**Usage**:

```bash
# List projects
gh projects list

# Add item to project
gh projects item-add <project-id> --owner <owner> --url <issue-url>
```

**Recommendation**: High value for roadmap agent integration.

---

#### `gh-workon` (chmouel/gh-workon)

**Purpose**: Create branch from issue and auto-assign.

**Workflow Fit**: Reduces manual steps in issue-to-branch workflow.

**Agent Compatibility**: Yes. Simple CLI interface.

**Value Add**: Automates branch creation with issue context.

**Installation**:

```bash
gh extension install chmouel/gh-workon
```

**Usage**:

```bash
# Create branch from issue 123
gh workon 123

# Creates branch like "issue-123-feature-title"
# Assigns issue to you
# Checks out branch
```

**Recommendation**: Medium value. Our workflows typically create branches manually with descriptive names.

---

### Medium Priority

Useful but not critical for current workflows.

#### `gh-sql` (KOBA789/gh-sql)

**Purpose**: Query GitHub Projects with SQL.

**Workflow Fit**: Advanced project analytics and reporting.

**Agent Compatibility**: Yes. SQL query interface.

**Value Add**: Complex project queries without GraphQL.

**Installation**:

```bash
gh extension install KOBA789/gh-sql
```

**Usage**:

```bash
# Query project items
gh sql "SELECT title, status FROM items WHERE assignee = '@me'"
```

**Recommendation**: Low priority until project board usage increases.

---

#### `gh-repo-explore` (multiple implementations)

**Purpose**: Interactive repository browsing.

**Workflow Fit**: Manual code exploration.

**Agent Compatibility**: No. Interactive TUI.

**Value Add**: None for automation. Use Serena symbolic tools instead.

**Recommendation**: Skip. Not suitable for agent workflows.

---

### Low Priority

Extensions that duplicate existing functionality or provide minimal value.

#### `gh-changelog` / `gh-gh-changelog`

**Purpose**: Generate changelogs from commits.

**Workflow Fit**: Release automation.

**Agent Compatibility**: Yes.

**Value Add**: Limited. GitHub releases already generate release notes.

**Recommendation**: Low value. GitHub native release notes are sufficient.

---

#### `gh-clean-branches` / `gh-poi`

**Purpose**: Cleanup local branches.

**Workflow Fit**: Local repository maintenance.

**Agent Compatibility**: Yes.

**Value Add**: Minimal. `git branch -d` works fine.

**Recommendation**: Skip. No significant value add.

---

#### `gh-semver`

**Purpose**: Calculate next semantic version.

**Workflow Fit**: Release versioning.

**Agent Compatibility**: Yes.

**Value Add**: Limited. Manual versioning is explicit.

**Recommendation**: Low value. Keep versioning explicit.

---

## Not Recommended

Extensions that failed evaluation criteria.

| Extension | Reason |
|-----------|--------|
| `gh-cp` | Duplicates `gh api` for file download |
| `gh-download` | Duplicates `gh api` and git operations |
| `gh-clone-org` | Niche use case, not needed |
| `gh-subrepo` | Submodule complexity, avoid |
| `gh-describe` | Solves shallow clone issue, not applicable |
| `gh-collab-scanner` | Limited value, manual inspection sufficient |

---

## Evaluation Criteria

Each extension was evaluated on four dimensions:

### 1. Workflow Fit

Does it complement existing GitHub skill scripts?

- ✅ Provides capability we lack
- ⚠️ Overlaps with existing scripts
- ❌ Duplicates functionality

### 2. Maintenance

Is the extension actively maintained?

- ✅ Commits within 6 months, responsive maintainer
- ⚠️ Commits within 12 months
- ❌ Stale (no commits 12+ months)

### 3. Agent Compatibility

Can it be invoked programmatically?

- ✅ CLI with JSON output, exit codes
- ⚠️ CLI but limited output formatting
- ❌ Interactive TUI only

### 4. Value Add

Does it reduce manual steps or enable new capabilities?

- ✅ Significant time savings or new capability
- ⚠️ Marginal improvement
- ❌ No meaningful benefit

---

## Discovery Commands

```bash
# Browse extensions interactively
gh extension browse

# Search by keyword
gh extension search <keyword>

# Install extension
gh extension install owner/gh-extension-name

# List installed extensions
gh extension list

# Upgrade all extensions
gh extension upgrade --all

# Remove extension
gh extension remove <name>
```

---

## Integration Guidelines

When adding extension wrapper scripts to GitHub skill:

### Structure

```text
.claude/skills/github/scripts/extensions/
├── README.md
├── gh_projects_add_item.py
├── gh_projects_list.py
└── gh_workon.py
```

### Script Template

```python
#!/usr/bin/env python3
"""
Wrapper for gh extension: <extension-name>

Purpose: <one-line description>
Extension: owner/gh-extension-name
"""

import subprocess
import json
import sys

def run_extension():
    """Execute gh extension with error handling."""
    try:
        result = subprocess.run(
            ["gh", "extension-command", "args"],
            capture_output=True,
            text=True,
            check=True
        )

        return {
            "success": True,
            "data": result.stdout
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr
        }

if __name__ == "__main__":
    result = run_extension()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
```

### Testing

```bash
# Verify extension installed
gh extension list | grep <extension-name>

# Test wrapper script
python3 .claude/skills/github/scripts/extensions/<script>.py

# Verify JSON output
python3 <script>.py | jq .
```

---

## Contributing Improvements Upstream

If you identify issues or enhancements while using extensions:

1. Open issue in extension repository
2. Submit PR with fix
3. Reference our use case
4. Document in `.agents/sessions/YYYY-MM-DD-session-NN.json`

---

## References

- [Awesome gh-cli extensions](https://github.com/kodepandai/awesome-gh-cli-extensions)
- [GitHub Blog: New GitHub CLI extension tools](https://github.blog/developer-skills/github/new-github-cli-extension-tools/)
- [gh extension documentation](https://cli.github.com/manual/gh_extension)

---

## Maintenance

**Last Reviewed**: 2026-02-23
**Next Review**: 2026-05-23 (quarterly)
**Reviewer**: @rjmurillo-bot

Review checklist:

- [ ] Check for new extensions in awesome-gh-cli-extensions
- [ ] Verify installed extensions still maintained
- [ ] Test agent compatibility of recommended extensions
- [ ] Remove stale extensions
- [ ] Update installation instructions
