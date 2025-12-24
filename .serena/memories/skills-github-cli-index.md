# GitHub CLI Skills Index

**Domain**: GitHub CLI (`gh`) command patterns and automation
**Skills**: 50+
**Updated**: 2025-12-23

## Activation Vocabulary

| Keywords | File |
|----------|------|
| pr create review merge list approve squash draft fill auto-merge delete-branch | github-cli-pr-operations |
| issue create edit close reopen lock pin transfer lifecycle assignee milestone label | github-cli-issue-operations |
| copilot copilot-swe-agent assign trigger automated resolution context injection | github-cli-issue-operations |
| run workflow list view log-failed watch trigger dispatch inputs status failure | github-cli-workflow-runs |
| release create upload download assets generate-notes draft prerelease changelog tag | github-cli-releases |
| api graphql paginate jq query mutation REST endpoint header cache slurp | github-cli-api-patterns |
| auth login token scope refresh project workflow packages logout switch | github-cli-api-patterns |
| json output jq filter transform select sort raw fields scripting | github-cli-api-patterns |
| repo edit settings visibility security fork sync deploy-key archive rename | github-cli-repo-management |
| secret set list env org dependabot codespaces variable encrypted | github-cli-secrets-variables |
| label create edit delete clone color description force standardize | github-cli-labels-cache |
| cache list delete all artifacts storage reclaim actions | github-cli-labels-cache |
| ruleset check compliance governance branch protected | github-cli-labels-cache |
| project create list item add field milestone owner close link template | github-cli-projects |
| extension install search upgrade browse remove exec sub-issue | github-cli-extensions |
| gh-dash gh-notify gh-metrics gh-combine-prs gh-milestone gh-hook gh-gr gh-grep | github-cli-extensions |
| anti-pattern pitfall rate-limit pagination repository-rename GITHUB_TOKEN error | github-cli-anti-patterns |
| attestation verify provenance supply-chain security artifact OCI container | github-cli-anti-patterns |

## Coverage

| File | Skills | Category |
|------|--------|----------|
| github-cli-pr-operations | PR-001 through PR-004 | Pull Request lifecycle |
| github-cli-issue-operations | Issue-001 through Issue-003, Copilot-001 | Issue management |
| github-cli-workflow-runs | Run-001, Run-002 | Workflow automation |
| github-cli-releases | Release-001, Release-002 | Release management |
| github-cli-api-patterns | API-001, GraphQL-001, Auth-001, JSON-001 | API and authentication |
| github-cli-repo-management | Repo-001 through Repo-004 | Repository settings |
| github-cli-secrets-variables | Secret-001, Variable-001 | Secrets management |
| github-cli-labels-cache | Label-001, Label-002, Cache-001, Ruleset-001 | Metadata and cache |
| github-cli-projects | Project-001, Project-002 | GitHub Projects v2 |
| github-cli-extensions | Extension-001 through Ext-GR-001 | CLI extensions |
| github-cli-anti-patterns | Anti-Pattern-001 through 009, Attestation-001 | Pitfalls and security |

## Related

- Source: GitHub CLI Manual, Session 56, PRs #88, #90, #212
- PR review workflow: `skills-pr-review`
- Workflow patterns: `skills-github-workflow-patterns`
