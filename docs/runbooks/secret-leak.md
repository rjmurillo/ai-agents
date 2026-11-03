# Leaked secret

## Symptom

A credential reached a place others can read: a commit, a PR or issue body, a
comment, a workflow log, a session log, or a retrospective. Examples are a
GitHub token, an npm token, or a model provider API key.

## Confirm

1. Identify the credential and where it appeared. Do not paste the value into a
   new issue, comment, or chat to ask about it.
2. Map it to its secret. The workflows read these repository secrets, among
   others: `BOT_PAT`, `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`,
   `COPILOT_GITHUB_TOKEN`, and `NPM_TOKEN` (the last one in the `npm`
   environment).
3. Treat the secret as exposed from the moment it was pushed. A revert or an
   edit does not remove it from history, forks, caches, or notification email.

## Recover

1. **Revoke or rotate the credential first.** Do it at the issuer: GitHub token
   settings, npm token settings, or the model provider console. Then store the
   new value in
   [Settings > Secrets and variables > Actions](https://github.com/rjmurillo/ai-agents/settings/secrets/actions)
   or in the `npm` environment. Only a repository admin can change these.
2. **Remove it from the current tree.** Delete the value on a branch and open a
   PR with the `push-pr` skill. That PR's diff still shows the old value in its
   removed lines, so this step does not end the exposure. Rotation does.
   For a PR body, issue body, or comment, editing the text is not enough: GitHub
   keeps the earlier revision in the edit history. Delete that revision from the
   edit history, or delete the comment. To scrub free text before you post it,
   run the redactor on a file:

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
