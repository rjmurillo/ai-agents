# Debate Log: ADR-068 UserPromptSubmit Reversion

PR #5350 restores ADR-068 to `origin/main`.

## Decision under review

Remove the PR's UserPromptSubmit amendment. Restore the accepted policy that
Copilot config-file UserPromptSubmit output stays suppressed.

The PR had promoted a Copilot CLI 1.0.79-6 runtime observation into current
authoring guidance. It then selected the output protocol through inherited
environment variables that do not identify the consuming host.

## Evidence

1. GitHub's current hook reference states that `modifiedPrompt` applies only
   to SDK programmatic hooks.
2. The same reference states that command and HTTP config-file
   `userPromptSubmitted` output is dropped.
3. The source update landed in `github/docs` commit
   `2da8026e59d82cab15e5cf316a85d30877bcec60` on 2026-08-26.
4. The PR's `COPILOT_CLI` selector was not vendor-confirmed.
5. The PR made branch-controlled `.serena/memories` text model-visible under
   the unsupported path.
6. The prior debate log used one reviewer. The ADR review skill requires six.

Official source:
<https://github.com/github/docs/blob/2da8026e59d82cab15e5cf316a85d30877bcec60/content/copilot/reference/hooks-reference.md>

## Round 1

Six roles reviewed the staged ADR restoration and its then-incomplete
collateral state.

| Role | Vote | Finding |
|---|---|---|
| architect | Accept | Reversion restores reviewed policy and changes no decision. |
| critic | Disagree-and-Commit | Remove false current-state claims from collateral files. |
| independent-thinker | Block | Restore collateral and preserve no false acceptance record. |
| security | Disagree-and-Commit | Keep suppression and remove envelope guidance. |
| analyst | Block | Resolve the partial-revert state before acceptance. |
| high-level-advisor | Block | Keep launcher concerns separate from the ADR decision. |

Round 1 found no P0 issue in the ADR restoration. Its blockers concerned
collateral files that still described removed code.

## Resolution

The branch restored these surfaces to `origin/main`:

- memory-recall runtime and host-selection tests;
- UserPromptSubmit suppression policy and generated mirrors;
- agent-harness contract skill and official sidecar;
- versioned probe sidecar and generated mirror;
- Serena memories and memory index;
- ADR-068 itself.

Issue #4727 remains open. A supported redesign belongs in a separate change.

## Round 2

All roles received the current vendor source and the complete restoration
plan.

| Role | Vote | Remaining P0 or P1 |
|---|---|---|
| architect | Accept | None. |
| critic | Accept | None. |
| independent-thinker | Accept after restoration | None after the listed files return to main. |
| security | Accept | None. |
| analyst | Accept | None. |
| high-level-advisor | Accept | None. |

The independent-thinker vote named one condition: restore the remaining
sidecars and remove the prior false debate record. This change satisfies that
condition.

## Strategic checks

- Chesterton's Fence: pass. The existing suppression protects model context.
- Path dependence: pass. Git history preserves the abandoned experiment.
- Core versus context: not applicable. No new capability ships.
- Second-system effect: pass. Reversion removes the unsupported mechanism.

## Outcome

Accepted, 6 of 6. ADR-068 returns to the reviewed `origin/main` text.

This log validates the reversion commit. A following commit removes the log
because the final PR has no ADR change.
