# ADR Debate Log: ADR-068 Amendment for Copilot Memory Recall (Issue #4727)

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-068-consolidated-hook-dispatcher.md`
- **Change**: amendment dated 2026-09-26, issue #4727
- **Rounds**: 2
- **Outcome**: Consensus
- **Final Status**: accepted
- **Final vote**: 2 Accept, 4 Disagree-and-Commit, 0 Block

The six roles ran in two reviewer agents, three roles each. The owner caps a
session at three subagents, so one agent per role was not possible. Each agent
read the amendment, the full diff, and the pinned GitHub hook reference.

## Decision Under Review

Copilot CLI drops command and HTTP config-file `userPromptSubmitted` output.
The `.claude/settings.json` recall hook therefore does nothing under Copilot.
The owner chose a direct `.github/hooks/memory-recall.json` registration on
`userPromptTransformed`. It appends the `<memory-context>` block through the
documented `modifiedTransformedPrompt` field. This is an explicit exception to
the branch-controlled prose policy, limited to memory recall.

Prior attempt PR #5350 branched on `COPILOT_CLI` and emitted
`additionalContext` on UserPromptSubmit. It was reverted because the docs say
that output is dropped and issue #5369 found `COPILOT_CLI` unconfirmed.

## Round 1 Summary

### Agent Positions

| Agent | Position | Key concern |
|-------|----------|-------------|
| architect | Disagree-and-Commit | Stale "no documented output field" text in ADR-068 Decision item 3, Implementation Notes, `generate_hooks_emit.py`, and the portability-campaign skill; Status line missing the amendment |
| critic | Disagree-and-Commit | Amendment ignored the cloud agent; batched submissions and resume replay not stated |
| independent-thinker | Block | Cloud agent runs a pull request branch's `.serena/memories` unattended with pre-approved tools; residual understated |
| security | Disagree-and-Commit | `modifiedTransformedPrompt` persists in session history and replays on resume; cloud agent exposure not addressed |
| analyst | Accept | Claims verified against the pinned hook reference; review diff omitted mirror files |
| high-level-advisor | Disagree-and-Commit | Scope right; land the two security text fixes before merge |

### Key Issues Addressed

- P0 (independent-thinker): cloud agent exposure. Put to the owner as a
  decision. The owner chose to exclude the cloud agent.
- P1 (security, critic): resume persistence and batched submissions not
  recorded.
- P1 (architect): stale statements in ADR-068 and three other files.
- P1 (independent-thinker): the rule presented delivery as working while the
  live probe was blocked.

### Major Changes Made

- The Copilot recall hook (`user_prompt_transformed_memory.main`) prints
  nothing when `COPILOT_AGENT_PROMPT` or `GITHUB_COPILOT_API_TOKEN` is set. The hook reference documents both as
  cloud agent sandbox variables. Unit and subprocess tests cover it.
- The amendment gained bullets for cloud exclusion, resume persistence,
  batched submissions, "registered, delivery unverified" status, and the two
  superseded statements. The Status section now cites the amendment.
- Stale text fixed in `build/scripts/generate_hooks_emit.py`,
  `templates/skills/ai-agents-portability-campaign.SKILL.md.tmpl`,
  `build/AGENTS.md`, and the generated-artifacts rule and its fixture.
- The round 2 diff included every mirror, the Serena memory, and the fixture.

## Round 2 Summary

### Agent Positions

| Agent | Position | Note |
|-------|----------|------|
| architect | Disagree-and-Commit | Env-var wording in the amendment contradicted the new cloud guard |
| critic | Disagree-and-Commit | Same wording issue |
| independent-thinker | Disagree-and-Commit | Moved from Block after the cloud exclusion landed |
| security | Accept | Both round 1 items resolved |
| analyst | Disagree-and-Commit | Same wording issue in ADR-068 and `probe-evidence.md` |
| high-level-advisor | Accept | P2 deferrals acceptable |

### Key Issues Addressed

- The amendment and `probe-evidence.md` said no environment variable is read.
  Both now say the event selects the host and the only variables read are the
  two cloud exclusion variables.
- `build/AGENTS.md` still called binplace the sole writer of `.github/hooks/`.
  It now names the `memory-recall.json` exception.
- `.serena/memories/copilot-hook-generation-invariants.md` still said
  UserPromptSubmit had no documented output field. Corrected.

## Deferred (P2)

- `_format_memory_context` does not escape a closing `</memory-context>` tag
  inside a memory title or snippet. This predates the change and affects the
  Claude path too.
- Memory titles have no length cap. Snippets are capped at 200 characters and
  results at three.
- No test enforces the 10-second `timeoutSec` budget.
- Live delivery on Copilot CLI 1.0.89-1 is unverified. The account's request
  quota was exhausted on 2026-09-26.

## Next Steps

None for the ADR. The deferred items are listed in the pull request body for
the owner's decision.
