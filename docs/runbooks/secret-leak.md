# Leaked secret

## Symptom

A credential reached a place others can read: a commit, a PR or issue body, a
comment, a workflow log, a session log, or a retrospective. Examples are a
GitHub token, an npm token, or a model provider API key.

## Confirm

1. Identify the credential and where it appeared. Do not paste the value into a
   new issue, comment, or chat to ask about it.
2. Map it to its secret and where it lives. Each provider key lives in one
   `agent-*` environment (ADR-114 decision 1). ADR-114 decision 11 item 4 lists
   two repository-level copies as still open on 2026-10-07:

   | Secret | Where it lives |
   |---|---|
   | `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` | `agent-claude` environment |
   | `COPILOT_GITHUB_TOKEN` | `agent-copilot` environment |
   | `OPENAI_API_KEY` | `agent-codex` environment |
   | `FACTORY_API_KEY` | `agent-droid` environment, plus a repository-level copy |
   | `SMOKE_ANTHROPIC_API_KEY` | Repository level |
   | `TRUNK_API_TOKEN` | Repository level |
   | `ADR101_PUBLISHER_APP_PRIVATE_KEY` | Read by `adr101-publisher.yml` from environment `adr101-publisher` |
   | `NPM_TOKEN` | Read by `publish.yml` from environment `npm` |
   | `BOT_PAT` | Repository level, if set. ADR-114 decision 11 found no copy on 2026-10-07 |

   The repository and environment secret lists above were read with the
   GitHub API on 2026-11-05. On that date the live environment list held
   `agent-claude`, `agent-codex`, `agent-copilot`, `agent-droid`,
   `bot-secrets`, and `copilot`. It held no `npm` or `adr101-publisher`
   environment, and no `NPM_TOKEN` or `ADR101_PUBLISHER_APP_PRIVATE_KEY`
   secret at repository level. `publish.yml:230` and `adr101-publisher.yml:119`
   still name those two environments. Check the live list before you rely on
   the table. An environment created by hand, or by the first workflow run that
   names it, has no required reviewers until an admin adds them. On 2026-11-05
   the four `agent-*` environments had required reviewers and `bot-secrets` and
   `copilot` had none.

   Workflows under `.github/workflows/` name most of these secrets and the job
   `environment:` that reads it. None of them names `OPENAI_API_KEY`,
   `FACTORY_API_KEY`, `SMOKE_ANTHROPIC_API_KEY`, or `TRUNK_API_TOKEN`, so
   search `scripts/` and the secret lists for those four. ADR-114 decision 11
   records the owner's last check of where each secret lives.
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
   also reaches jobs outside the environment's reviewer gate. If the table
   lists a repository copy for the secret, or you find one, update or delete it
   too, in
   [Settings > Secrets and variables > Actions](https://github.com/rjmurillo/ai-agents/settings/secrets/actions).
   The table lists repository-level secrets, and those are the ones that
   belong there. Only a repository admin can change these.
2. **Remove it from the current tree.** Delete the value on a branch and open a
   PR with the `push-pr` skill. That PR's diff still shows the old value in its
   removed lines, so this step does not end the exposure. Rotation does.
   For a PR body, issue body, or comment, editing the text is not enough: GitHub
   keeps the earlier revision in the edit history. Delete that revision from the
   edit history, or delete the comment. For a workflow log, delete the logs of
   the affected run from its Actions page, which needs write access. Workflow
   artifacts can also hold the value. Open the run's Artifacts section, check
   each artifact, and delete any that contains it. To scrub
   free text before you post it, run the redactor on a file:

   ```bash
   uv run --frozen python scripts/redact_secrets.py <file>
   ```

   The redactor prints the text to stdout with token shapes replaced. It does
   not change the file, and it does not scan the repository. It matches known
   token shapes only. A value in another shape passes through, so clean output
   does not prove the text is safe to post. Read the output yourself.
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
