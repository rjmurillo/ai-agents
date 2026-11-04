# Bad plugin or package release

This repository ships two things that users install, and they roll back in
different ways.

| Artifact | How users get it | Versioned? |
|---|---|---|
| `project-toolkit@ai-agents` plugin | Claude Code or Copilot CLI marketplace, from `main` | No. Plugins carry no manifest version (ADR-092), so each update takes the latest `main` |
| `@rjmurillo/ai-agents` npm package | `npm` or `npx` | Yes, from `packages/ai-agents-cli/package.json` |

## Symptom

- Users report that an agent, skill, or hook broke right after a plugin update.
- Users report that a new npm version fails to install or run.

## Confirm

1. Find the change. For a plugin report, list recent commits that touched the
   shipped trees:

   ```bash
   git log --oneline -20 origin/main -- src/claude src/copilot-cli .claude-plugin .github/plugin
   ```

2. For the npm package, check what is published. `version` reports only the
   `latest` dist-tag, and `versions` lists every published version:

   ```bash
   npm view @rjmurillo/ai-agents version
   npm view @rjmurillo/ai-agents versions
   ```

## Recover the plugin

Fix `main`. Every user gets `main` on the next plugin update, so a revert on
`main` is the rollback for everyone:

```bash
git switch -c fix/revert-<short sha> origin/main
git revert <sha>
```

Open the PR with the `push-pr` skill and merge it once checks pass. Then users
update:

- Claude Code: `claude plugin update project-toolkit@ai-agents`, or
  **Update now** on the **Installed** tab of `/plugin`.
- Copilot CLI: `copilot plugin update project-toolkit@ai-agents`.

A user who cannot wait for the fix can pin the marketplace to a release tag.
Tags are cut rarely, so a tag can be far behind `main`. List them with
`git tag --sort=-creatordate`. Pin to `v0.4.0` or later. Earlier tags carry no
`project-toolkit` entry in either marketplace, so the install step fails. Both CLIs accept `owner/repo#ref` for a
marketplace source. Remove the plugin and marketplace first, then add the
pinned marketplace and reinstall. Claude Code:

```text
/plugin uninstall project-toolkit@ai-agents
/plugin marketplace remove ai-agents
/plugin marketplace add rjmurillo/ai-agents#<tag>
/plugin install project-toolkit@ai-agents
```

Copilot CLI:

```bash
copilot plugin uninstall project-toolkit@ai-agents
copilot plugin marketplace remove ai-agents
copilot plugin marketplace add rjmurillo/ai-agents#<tag>
copilot plugin install project-toolkit@ai-agents
```

To unpin later, repeat the steps with `rjmurillo/ai-agents` and no `#<tag>`.

## Recover the npm package

Follow [RELEASING.md: Rollback procedures](../../RELEASING.md#rollback-procedures):

- Deprecate the bad version so installs show a warning:
  `npm deprecate @rjmurillo/ai-agents@X.Y.Z "reason"`.
- Publish a patch that supersedes it through the npm Publish workflow.
- Unpublish only a single version, and only within 72 hours of its publish.

Users can install a known good version with
`npm install @rjmurillo/ai-agents@X.Y.Z`.

## Escalate

The publish workflows belong to `@rjmurillo` (`.github/CODEOWNERS`). The npm
package and the marketplace manifests have no CODEOWNERS rule, so escalate to
the same maintainer directly. Only the owner can deprecate or unpublish on npm. If the
bad release exposes users to a vulnerability, report it through a private
advisory as [SECURITY.md](../../SECURITY.md) describes.

## Links

- [Installation guide](../installation.md)
- [Plugin commands reference (Claude Code)](https://code.claude.com/docs/en/plugins/cli-reference)
- [CLI plugin reference (Copilot CLI)](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)
