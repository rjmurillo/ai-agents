# A fresh scan found four times as many failing skills as the issue title claimed

**Atomicity**: 90%
**Category**: Issue triage
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E094. State checked on main at 1be533c496 (2026-11-26).

## Question

Can an issue's titled count be used to size work without re-measuring it?

## Conventional answer

Issue 3496 said 2 skills failed skillforge (2026-07-27). Issue 3509 said 22 of 212 rules had mentions, or 10.4% (2026-07-27).

## First-principles position

The repo-wide scan found eight failures on 2026-07-27. Lefthook checked only staged files, so it could not report a repo-wide count. The rule mention rate also changed when measured on a different corpus. Two other claims reproduced exactly.

## Evidence with limits

- Issue 3496: a repo-wide scan found 8 of 96 skills failing skillforge (2026-07-27). The title said 2.
- `lefthook.yml:120` ran the check on staged files only.
- Issue 3509: re-measured at 4.0% (17 of 422) on a single-user corpus, against the titled 10.4% (22 of 212) reported in the 2026-07-27 session.
- Issues 3494 and 3457 reproduced exactly.
- Limits: The 17 of 422 figure is quoted from issue 3513, not run in this session. The hook is still staged-only at `lefthook.yml:215-218`. All 121 skills pass on 2026-11-26.
- State on main at 1be533c496 (2026-11-26): fixed for the count. skillforge fail=0 of 121 skills.

## Decision

Re-run an issue's measurement on current main before sizing work. A titled count can be off by 4x in either direction.
