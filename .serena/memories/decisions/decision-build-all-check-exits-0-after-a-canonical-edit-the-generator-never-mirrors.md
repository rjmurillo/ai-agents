# A generation check can pass without copying an edited source file

**Atomicity**: 90%
**Category**: Generated artifacts
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E143. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a passing `build_all.py --check` show that a source file reaches its mirror?

## Conventional answer

The generation check was expected to catch drift between a source file and its mirror.

## First-principles position

A marker added to `push_guard_base.py` never reached the Copilot mirror. The check still exited 0 with no drift output. Its pass covered the generator's configured inputs only.

## Evidence with limits

- The probe appended a marker to the source `push_guard_base.py` in a scratch worktree (2026-08-13).
- `build_all.py --check` exited 0 with no drift output (2026-08-13).
- A search for the marker in `src/copilot-cli/hooks/PreToolUse/push_guard_base.py` returned no matches (2026-08-13).
- `_COMPANIONS_BY_OWNER` had no entry for `invoke_markdownlint_guard.py` (2026-08-13).
- Limits: One file probed on 2026-08-13. The Copilot hook tree is absent on pinned main, so this gap no longer applies.
- State on main at 1be533c496 (2026-11-26): superseded. `build/scripts/generate_hooks_events.py:71` defines `_COMPANIONS_BY_OWNER` as an empty dict.

## Decision

Treat a passing `build_all.py --check` as proof only for configured inputs. In a scratch worktree, mark the source and check the mirror before claiming coverage.

## Related

- `.serena/memories/decision-a-gate-with-no-inputs-passes-forever.md`
- `.serena/memories/ci/ci-build-all-check-reports-uncommitted-changes-as-drift.md`
