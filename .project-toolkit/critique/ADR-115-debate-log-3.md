# ADR Debate Log: ADR-115 Muse Personal Agent and Muse Code Targets

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-2.md` (consensus in round 3, 2026-11-11)
- **Trigger**: owner decision, Richard, 2026-11-11: "For muse, we need to target both muse code and muse personal agents."
- **Panel**: reduced (architect and critic). Prose decisions only.
- **Design input**: a separate architect consult chose one `src/muse/` tree for both targets, with one install section per target and agents for Muse Code only.

## Pre-review evidence

- Muse Code 1.4.15 in a scratch home, no login, 2026-11-11: `muse skills validate <dir> --json` reported all 105 skills in `src/muse/skills/` and all 105 in `src/codex/skills/` as valid and `compatible`. A `SKILL.md` with no `description` was rejected.
- The Muse Code changelog entry for 1.4.9 names `request_user_input` (raw page read 2026-11-11).

## Round 1

### Architect

Vote: Disagree-and-Commit.

- P1: the validate run was cited as proving the bytes suit both targets; it tested Muse Code only.
- P1: `request_user_input` and the Muse Code `lib/` location had no source or measurement.
- P1: the personal-agent target has no recorded run in its host (MUST NOT 2).
- P2: Decision 1 still said 97 skills; each tree holds 105.

### Critic

Vote: Block.

- P1: the same over-reach of the validate run.
- P1: Codex and Muse copies in a repository's `.agents/skills/` replace each other; naming the overlap is not enough.
- P1: `request_user_input` unsourced.
- P1: the Muse Code `lib/` location is a guess under Decision 9.
- P2: the shared dispatch text should say `subagent_spawn` is Muse Code only.

### Changes made after round 1

- Decision 8: "Both targets install the same tree. The `muse skills validate` run shows Muse Code accepts it; the personal agent has no validator."
- Decision 8 quotes the Muse Code changelog for `request_user_input`.
- Decision 8: the `lib/` location is what the scripts resolve and the install test replays; whether a Muse Code session runs scripts from there is recorded as not measured, and the owner's Muse Code run must run one script-backed skill.
- Decision 8: Muse Code skills install to the user root `~/.agents/skills` only; the guide says not to copy them into a repository's `.agents/skills/`.
- Decision 8 and Deferred Items: the personal-agent target gets nothing new here; its PR #7041 ship has no recorded host run, a pre-existing MUST NOT 2 gap that needs an owner run.
- Decision 13 says `subagent_spawn` is Muse Code only.
- Decision 1: 105 skills, counted 2026-11-11.

## Round 2

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. All round 1 items resolved. Notes that personal-agent skills stay shipped without a host run until the deferred owner run. |
| critic | Accept. All round 1 items resolved. New P2: Codex may also read `~/.agents/skills`, so a Muse Code install there would duplicate skills for a Codex user. |

### Changes made after round 2

- Measured the P2 the same day: Codex 0.167.0 with a scratch `HOME` listed a probe skill from `~/.agents/skills` and did not list it once the skill was moved away. The Muse Code docs also name the Muse-only user root `$XDG_CONFIG_HOME/muse/skills`. Decision 8 now installs Muse Code skills and `lib/` under `${XDG_CONFIG_HOME:-~/.config}/muse/` and tells users not to use either `.agents/skills` root. This narrows the install target; no decision changed, so no further round ran.

## Outcome

Outcome: Consensus in round 2, both reviewers Accept. One `src/muse/` tree serves the Muse personal agent (skills and `lib/` only) and Muse Code (skills, `lib/`, and agents). The ADR stays `proposed`.
