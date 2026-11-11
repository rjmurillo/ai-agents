# ADR Debate Log: ADR-115 Amendment for Codex and Muse Code Agents

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log.md` (closed by consensus in round 5, with owner amendments on 2026-10-13)
- **Trigger**: issue #7226. Codex and Muse skills dispatch agents those trees do not ship. The owner approved the plan in the issue's part 3 research comment on 2026-11-11: ship agents to Codex and Muse Code, and make dispatch lines host-neutral.
- **Panel**: reduced (architect and critic). The amendment changes prose decisions, not an executable gate that other gates read.
- **Started**: 2026-11-11

## Pre-review evidence

- Codex 0.167.0, measured 2026-11-11: `codex debug prompt-input` lists loaded custom agents with no login. A project agent loads only in a trusted project. A file without `developer_instructions` does not load.
- Muse Code docs, fetched 2026-11-11 from <https://dev.meta.ai/docs/muse-code/agents>: frontmatter keys `name`, `description`, `model`, `effort`, `tools`, `disallowedTools`; an unrecognized key makes the agent unspawnable. No official page names `~/workspace/custom-skills/`.
- Muse Code 1.4.15, installed into a scratch home 2026-11-11: the `echo` provider with `--trust-workspace` printed no agent list and no error for an agent with an unknown key.
- A design review by the architect before drafting found six defects, recorded in the PR description for the implementation pull requests.

## Round 1

### Architect

Vote: Disagree-and-Commit.

- P0: Decision 8 required an owner-run Muse test while Deferred Items deferred the same test.
- P1: Decision 1, Decision 11, and Decision 10 still described the Muse manifest that was never built.
- P1: the `disallowedTools` carve-out redefined Decision 3's rule instead of recording an exception, since `Agent` is a Claude Code tool.
- P1: the permission-boundary claim had no quoted source.
- P1: Consequences did not mention agents.
- P2: Decision 12, the Decision 8 install-guide sentence, and the status paragraph's subject after the index strip.
- Dissent: stretching the rule's meaning sets a precedent later hosts will cite. Record it as an exception.

### Critic

Vote: Block.

- P0: skills in `src/codex/skills` and `src/muse/skills` still dispatch `analyst`, `security`, and `code-reviewer`, which do not ship there. The appended paragraph reaches agent bodies only.
- P1: the same three stale Muse manifest lines the architect found.
- P1: the Codex installer contract lacked uninstall, a `CODEX_HOME` rule, a write order, a namespace warning, and per-behavior tests.
- P1: the Muse merge condition did not define the test's assertions, and the guide-only install path had no stated debt.
- P2: the Muse key gate allowed keys the build drops; the permission claim lacked a quote; `fork_turns="none"` had no carrier into the copied skills.

### Changes made after round 1

- Deferred Items: the Muse load test is no longer deferred; a Muse CI leg and a Muse installer are.
- Decisions 1, 10, 11, 12, and the Decision 8 guide sentence carry dated amendments that retire the Muse manifest text.
- Decision 3: the `disallowedTools` drop is an accepted, bounded exception, with quoted Codex and Muse Code sources.
- Decision 7: installer `CODEX_HOME` rule, write order with adoption of matching files, `--uninstall`, namespace warning, and a list of required unit tests.
- Decision 8: the owner-run Muse test must show each shipped agent spawns and a control agent with an unknown key does not. The guide-only install is accepted debt.
- Decision 11: the Muse gate checks exactly `name` and `description`.
- New Decision 13: dispatching skills name each host's tool, `fork_turns="none"` for reviewers on Codex, and an in-session fallback when no tool or agent exists. A gate fails when a shipped skill dispatches with `Task(` and lacks that text. This answers the critic's P0 and P2 on `fork_turns`.
- Consequences list the agents and the trade-offs.
- Status: "ADR-115 refines" gives the first paragraph a subject after the index strip.

## Round 2

### Architect

Vote: Disagree-and-Commit. Every round 1 finding is resolved.

- P1: Decision 13 named the Muse tool `subagent_spawn` while the host facts said no page lists Muse tool names.
- P2: the Neutral consequence credited text changes only to Decision 9; Decision 2 did not say the appended paragraph carries the fallback; Decision 11 had a spliced sentence.
- Dissent: the tool name must be sourced or removed before acceptance.

### Critic

Vote: Block, narrowly. Every round 1 finding is resolved.

- P1: the same unsourced `subagent_spawn` name.
- P2: the Decision 13 gate keyed on `Task(` misses prose dispatch such as "Use Task with the read-only `code-reviewer` subagent_type" in `dx-review`.

### Changes made after round 2

- The host facts now quote the Muse Code subagent fan-out cookbook, which names `subagent_spawn` with `role`. The narrower claim stays: no page lists the names a `tools` list accepts. Decision 8 and Decision 13 use that wording and cite the cookbook.
- The Decision 13 gate also matches `subagent_type`, with a prose fixture.
- Decision 2 says the appended paragraph tells the agent to do the step itself.
- The Neutral consequence names Decision 13.
- Decision 11's spliced sentence is split.

## Round 3

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. All round 2 items resolved. |
| critic | Accept. All round 2 items resolved. One non-blocking P2: Decision 13 named only `role`, while the cookbook names `role`, `objective`, and `worktree_isolation: true`. |

### Changes made after round 3

- Decision 13 names `objective` and `worktree_isolation: true` for a child that writes files.

## Outcome

Outcome: Consensus in round 3, both reviewers Accept. The ADR stays `proposed`; acceptance is the owner's call. Implementation follows in separate pull requests: Codex agents, Muse agents (merges only after the owner-run Muse Code test in Decision 8), host-neutral dispatch (Decision 13), and the `/review` fallback.
