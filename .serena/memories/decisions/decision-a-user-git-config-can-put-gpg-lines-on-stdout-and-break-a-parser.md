# Git signature output can corrupt parsed commit timestamps

**Atomicity**: 90%
**Category**: Git output parsing
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E102. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a timestamp parser trust `git show` to print only the requested date format?

## Conventional answer

A passing episode validator was taken as proof that the commit timestamps were correct.

## First-principles position

With `log.showSignature` enabled, `git show` printed signature messages on stdout before the date. The parser read those lines as timestamp data. The episode validator missed the corruption.

## Evidence with limits

- `git config --get log.showSignature` returned `true` (2026-08-02).
- `git show -s --format=%cI` printed 3 GPG lines on stdout before the date (2026-08-02).
- Limits: The probe covered one signing configuration on 2026-08-02. The reported count of other affected episodes was not verified.
- State on main at 1be533c496 (2026-11-26): still wrong. `src/claude/skills/memory/scripts/extract_session_episode.py:619` and `:2152` read commit timestamps without disabling signature output.

## Decision

Disable signature output when parsing Git stdout. Pass `--no-show-signature` or set `-c log.showSignature=false` on the Git call. The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.
