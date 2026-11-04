# Leaked secret

## Symptom

A credential reached a place others can read: a commit, a PR or issue body, a
comment, a workflow log, a session log, or a retrospective. Examples are a
GitHub token, an npm token, or a model provider API key.

## Confirm

1. Identify the credential and where it appeared. Do not paste the value into a
   new issue, comment, or chat to ask about it.
2. Map it to its secret and where it lives. Each provider key lives in one
   `agent-*` environment, with no repository-level copy (ADR-114 decision 1):

   | Secret | Where it lives |
   |---|---|
   | `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` | `agent-claude` environment |
   | `COPILOT_GITHUB_TOKEN` | `agent-copilot` environment |
   | `ADR101_PUBLISHER_APP_PRIVATE_KEY` | `adr101-publisher` environment |
   | `NPM_TOKEN` | `npm` environment |
   | `BOT_PAT` | Repository level, if set. ADR-114 decision 11 found no copy on 2026-10-07 |

   The workflows under `.github/workflows/` name each secret and the job
   `environment:` that reads it. ADR-114 decision 11 records the owner's
   last check of where each secret lives.
3. Treat the secret as exposed from the moment it was pushed. A revert or an
   edit does not remove it from history, forks, caches, or notification email.

## Recover

1. **Revoke or rotate the credential first.** Do it at the issuer: GitHub token
   settings, the GitHub App settings, npm token settings, or the model provider
   console. Then store the new value where the table above says it lives. For
   an environment secret, open
   [Settings > Environments](https://github.com/rjmurillo/ai-agents/settings/environments),
   pick the environment, and update the secret there. Do not add a
   repository-level copy. The environment copy takes precedence over it, so
   jobs in that environment would keep the revoked value. A repository copy
   also reaches jobs outside the environment's reviewer gate. Only `BOT_PAT`
   goes in
   [Settings > Secrets and variables > Actions](https://github.com/rjmurillo/ai-agents/settings/secrets/actions).
   Only a repository admin can change these.
2. **Remove it from the current tree.** Delete the value on a branch and open a
   PR with the `push-pr` skill. That PR's diff still shows the old value in its
   removed lines, so this step does not end the exposure. Rotation does.
   For a PR body, issue body, or comment, editing the text is not enough: GitHub
   keeps the earlier revision in the edit history. Delete that revision from the
   edit history, or delete the comment. For a workflow log, delete the logs of
   the affected run from its Actions page, which needs write access. To scrub
   free text before you post it, run the redactor on a file:

   ```bash
   uv run --frozen python scripts/redact_secrets.py <file>
   ```

   The redactor prints the text to stdout with token shapes replaced. It does
   not change the file, and it does not scan the repository.
3. **Do not rewrite shared history yourself.** Force-pushing `main` is forbidden.
   History cleanup is the owner's decision, and rotation is what protects you.
4. **Check for misuse.** Review the issuer's audit log for the exposure window.
   Check recent workflow runs and package versions for activity you did not
   start.

## Escalate

Tell `@rjmurillo` the same day. If the leak lets an attacker affect users, such
as a token that can publish the npm package or push to `main`, report it through
a [private security advisory](https://github.com/rjmurillo/ai-agents/security/advisories/new)
as [SECURITY.md](../../SECURITY.md) describes. Do not open a public issue.

## Links

- [SECURITY.md](../../SECURITY.md)
- [Secret redaction rule](../../.claude/rules/secret-redaction.md)
- [ADR-114: agent workflow environments](../../.project-toolkit/architecture/ADR-114-agent-workflows-approval-and-non-blocking.md)
