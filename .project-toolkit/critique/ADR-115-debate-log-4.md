# ADR Debate Log: ADR-115 Subagent Consequence and Muse Test Status

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-3.md` (consensus in round 2, 2026-11-11)
- **Trigger**: owner request, Richard, 2026-11-14, to fix the open items from the v0.7.0 audit. One item was a stale line in Consequences, Negative.
- **Panel**: reduced (architect and critic). Prose only. No decision changes, and no gate reads this text.

## Pre-review evidence

- The stale line said 24 agents "can start subagents" on Codex and Muse Code, and that "Muse agents wait on an owner-run test".
- `build/scripts/agent_toml.py` defines `NO_SUBAGENTS`: "Do not start subagents. Do the work in this session." Its comment says the model may ignore it.
- On 2026-11-14, 24 of 25 files in `src/codex/agents/` and 24 of 25 in `src/muse/agents/` carry that text. `orchestrator` is the one without it.
- PR #7334 merged on 2026-11-12. Its body records runs 5 and 6 as passes with Muse Code 1.4.15, after four runs that did not pass.

## Round 1

### Architect

Vote: Disagree-and-Commit.

- P1: Decision 8 still said the Muse agents pull request "merges only after" the owner run.
- P1: the Cursor agents paragraph said 24 agents can start a subagent and did not name the body instruction.
- P2: front-matter `date` was 2026-11-11.
- P2: "passed twice ... on 2026-11-12" dated run 5 without evidence and hid the four runs that did not pass.

### Critic

Vote: Disagree-and-Commit.

- P1: "Codex and Muse Code cannot enforce `disallowedTools: Agent`" overstated the Muse case. The build drops the key because Muse Code documents no tool name for it.
- P2: "PR #7334 records both runs" hid that only run 6 kept its output.
- P2: "PR #7322 and PR #7334" did not say which one added `NO_SUBAGENTS`.

### Changes made after round 1

- The consequence now says the build drops `disallowedTools: Agent` for both hosts.
- It says `NO_SUBAGENTS` was added in PR #7322 and turned on for Muse in PR #7334.
- The Muse line names the four runs that did not pass, and credits saved output to run 6 only.
- Decision 8 gained a dated note that the run passed and PR #7334 merged on 2026-11-12.
- The Cursor agents paragraph gained a dated pointer to the body instruction.
- Front-matter `date` is 2026-11-14.

## Round 2

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit. All round 1 items resolved. New P1: Cursor drops the key too and gets no body section, and Consequences did not say so. |
| critic | Accept. All round 1 items resolved. P2: Decision 8 keeps the old present-tense sentence ahead of the dated note. |

### Changes made after round 2

- Consequences now says the Cursor tree drops the key and adds no section: 0 of its 28 agent files carry one, counted 2026-11-14.
- The Decision 8 sentence stays as written. The ADR keeps original text and adds dated notes, as its earlier amendments do.

## Outcome

Outcome: Consensus in round 2. The critic accepts, and the architect commits with the Cursor gap now recorded. The ADR stays `proposed`. The amendment changes no decision.

## Open item for the owner

Cursor agents have neither a host control nor a body instruction against starting subagents. This log records the gap. It does not decide whether the Cursor tree should carry the section.
