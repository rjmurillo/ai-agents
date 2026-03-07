# GitHub CLI Extensions Evaluation

## Context

Issue #182: Evaluate and document useful GitHub CLI extensions for AI agent workflows.

## Evaluation Completed

Created comprehensive `.claude/skills/github/EXTENSIONS.md` documentation with:

1. **Currently Installed Extensions**: 10 extensions with agent compatibility assessment
   - gh-act, gh-combine-prs, gh-copilot, gh-gr, gh-grep, gh-hook, gh-metrics, gh-milestone, gh-notify, gh-sub-issue

2. **Evaluation Criteria**: Four dimensions for assessing extensions
   - Workflow Fit: Complements existing GitHub skill scripts
   - Maintenance: Active development and maintainer responsiveness
   - Agent Compatibility: CLI with JSON output, exit codes
   - Value Add: Reduces manual steps or enables new capabilities

3. **Recommended Extensions by Priority**:
   - **High**: gh-projects (official projects API), gh-dash (visual dashboard), gh-workon (branch from issue)
   - **Medium**: gh-sql (project queries)
   - **Low**: gh-changelog, gh-clean-branches, gh-semver
   - **Not Recommended**: gh-cp, gh-download, gh-clone-org, gh-subrepo

4. **Integration Guidelines**: Script structure, template, and testing for adding extension wrappers

## Key Findings

- **Agent-friendly extensions**: Must provide CLI with structured output (JSON), not interactive TUI
- **gh-projects**: Official extension for GitHub Projects V2, high value for roadmap agent integration
- **gh-dash**: Excellent for manual developer use, but NOT suitable for automation (interactive TUI)
- **Maintenance matters**: Avoid extensions with no commits in 12+ months

## Cross-Session Context

For future work on GitHub skill extensions:

1. Start with gh-projects integration for roadmap planning
2. Use extension wrappers in `.claude/skills/github/scripts/extensions/`
3. Follow template pattern: Python script, JSON output, error handling
4. Test agent compatibility before recommending

## Commit

b250d84: docs(github): evaluate and document useful gh CLI extensions
