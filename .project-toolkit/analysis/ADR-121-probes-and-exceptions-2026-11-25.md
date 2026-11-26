# ADR-121: Host Probes and Remaining Nested-Form Sites, 2026-11-25

This record serves issue #7640. It holds the Copilot CLI and Codex probe
results and the sites that still carry the nested form after this change.

## Skills and baseline

At 0b31dc034 (2026-11-25), before this change, the seven skills were already
migrated. PRs #7373 and #7374 moved them. `plugin_run_fix.py --inventory` reported
0 invocations and 0 assignments in `templates/skills`. `LEGACY_SITE_BASELINE`
already held `templates/skills` at (0, 0).

| Skill | Pull request |
|---|---|
| `skill-bootstrap`, `push-pr` | #7373 |
| `autoplan`, `memory-maintenance`, `skillforge`, `repository-completion-proof`, `skillopt` | #7374 |

## Probes

Both probes used one fixture: a `rootprobe` skill with marker lines, a fenced
block, a `references/` file, an agent file (Copilot only), and the committed
locator. Both ran with `CLAUDE_PLUGIN_ROOT` and `COPILOT_PLUGIN_ROOT` unset.

| Host | Version | Command shape | Result |
|---|---|---|---|
| Copilot CLI | 1.0.116 | `copilot --plugin-dir <fixture> -p <prompt> --allow-all-tools` | UNAVAILABLE. "You have exceeded your monthly quota" (request de7a3ea2-4d30-4f58-8bcb-48aa5ab9f7e7). A run with a private `COPILOT_HOME` got the same error. |
| Codex | 0.172.0 | `codex exec -C <workspace> --skip-git-repo-check -s read-only <prompt>` | UNAVAILABLE. `codex login status` prints "Not logged in". The API returned 401 "Missing bearer or basic authentication". |

No probe question got an answer on either host. Every row stays unmeasured for
these versions.

An earlier dated record covers Codex 0.169.0:
`2026-11-16-agent-body-plugin-root-probes.md`. It found a skill body and an
agent body left literal, and no plugin-root variable in the skill's shell. It
did not measure a `references/` file, a locator run, or an installed plugin.

Resume: restore Copilot quota and log Codex in, then rerun both commands
against the fixture.

## Remaining nested-form sites

`git grep -nE 'COPILOT_PLUGIN_ROOT:-\$\{CLAUDE_PLUGIN_ROOT:-' -- templates/skills templates/rules src/claude`
after this change lists only these sites. `templates/skills` and
`templates/rules` hold none.

| Site | Mentions | Why it stays |
|---|---|---|
| `src/claude/skills/pr-review/pr-review-config.yaml` | 19 | Class G. The gate runs these commands with no shell (ADR-121 decision 1). |
| `src/claude/skills/github/scripts/pr/run_completion_gate.py` | 3 | Gate code that recognizes the legacy form. An edit changes the gate's frozen dispatch closure. |
| `src/claude/skills/github-url-intercept/scripts/test_url_routing.py` | 3 | Python that emits a command at run time, pinned by tests. It is code, not prose. A move to the locator changes its output. |
| `src/claude/skills/github/scripts/pr/detect_stale_bot_review.py` | 1 | Python that emits a command for a person to run. Same reason. |
| `src/claude/lib/bootstrap.py`, `src/claude/lib/hook_utilities/bootstrap.py` | 1 each | A docstring rendered from `scripts/hook_utilities/bootstrap.py`. It names the env-var order the bootstrap shares with the legacy form. |
| `src/claude/agents/code-reviewer.md`, `src/claude/agents/retrospective.md` | 1 each | Renders of `templates/agents`. The shared form stays for Codex, Muse, and VS Code. A Claude-only render would need the PR #7363 host mechanism. That adds bare Copilot paths the Copilot probe has not proven. |

The two runtime emitters are the last places a foreign root can still
displace a command. Moving them to the locator is follow-up work.
