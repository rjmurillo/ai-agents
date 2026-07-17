# Copilot CLI disableAllHooks on Windows

## Verified behavior

Copilot CLI 1.0.70 was probed from a trusted Windows worktree with the same
prompt and plugin set.

- Hooks enabled: a repository SessionStart marker executed and plugin hook
  output appeared.
- `disableAllHooks: true`: the repository marker did not execute and plugin
  hook output was absent.
- The CLI still logged plugin hook metadata as loaded. Loaded does not mean
  executed.
- Five Defender policy hooks still loaded. GitHub documents policy hooks as
  exempt from `disableAllHooks`.
- A disabled real-tool probe also produced zero hook stdout or stderr lines.

The setting is read when a new CLI session starts. Changing it does not repair
an already wedged session.

## Operational use

Treat `disableAllHooks` as a version-specific, approval-required, read-only
diagnostic procedure, not a selective repository-hook switch. It stops
repository, user, and plugin hook execution in the verified CLI version. Keep
the local setting visible, remove it after diagnosis, and start a hook-enabled
session before any mutation, commit, or push.

A selective frontier-model profile would require new dispatcher feature work.
Copilot CLI is maintenance-only, so the current path is to fix and rescope
existing hooks. No supported Copilot CLI 1.0.70 configuration was found that keeps plugin
hooks while disabling repository hooks.

## Evidence

Session 3042 recorded the controlled probe counts and timestamps in
`.agents/analysis/2026-07-14-hook-batching-determination.md`.

## Related

- [copilot-agent-frontmatter-ci-enforcement](copilot-agent-frontmatter-ci-enforcement.md)
- [copilot-agent-frontmatter-ci-review-fixes](copilot-agent-frontmatter-ci-review-fixes.md)
- [copilot-hook-generation-invariants](copilot-hook-generation-invariants.md)
- [copilot-hooks-observations](copilot-hooks-observations.md)
