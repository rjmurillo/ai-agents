# Agents opened the matching retrospective in 0 of 219 sessions that started on an issue with one

**Atomicity**: 90%
**Category**: Agent behavior, retrospectives
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E074. State checked on main at 1be533c496 (2026-11-26).

## Question

Does injecting retrospective content at session start make agents read prior learnings?

## Conventional answer

Putting retrospective content, or a pointer to it, in front of the agent at session start makes agents recall prior learnings.

## First-principles position

The transcript query found no matching file reads in eligible sessions. Matching issue titles to retrospective titles rarely found the right file. The query did not measure which sessions received the old injection. It shows rare file reads, but cannot isolate the effect of the injection.

## Evidence with limits

- Across 5,801 ai-agents sessions (measured 2026-11-21), 20 sessions (0.3%) touched any retrospective path.
- 219 sessions had a first prompt naming an issue that had an existing retrospective, across 17 distinct retrospectives (2026-11-21). 0 of the 219 opened the matching file.
- Title matching recalled the right retrospective for 3 of 25 issue or PR titles, at about 0.68s per prompt.
- Limits: Transcripts on one machine, matched by first prompt, so subagent lookups are missed. The agent inferred, and did not measure, that the old 4,000-character injection reached most of these sessions. Only 7 sessions saw the new guide. Measured 2026-11-21.
- State on main at 1be533c496 (2026-11-26): superseded. An amendment dated 2026-11-20 says the Context Loader hook no longer injects the latest retrospective. It prints a 770-byte static RETRO_LOOKUP_GUIDE (ADR-008).

## Decision

Do not assume a session-start pointer or injected text makes agents consult retrospectives. Rerun the transcript query 2 to 4 weeks after the guide ships. Retire the guide if the rate stays near 0%.
