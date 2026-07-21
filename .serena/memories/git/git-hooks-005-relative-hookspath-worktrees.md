# Historical Skill-Git-005: Relative core.hooksPath

**Status**: Superseded by the Lefthook migration on 2026-07-19.

## Current contract

Lefthook is the sole Git hook manager. `lefthook.yml` declares the events, filters, named jobs, and validator commands. Human setup is:

```bash
uv run --frozen lefthook install
uv run --frozen lefthook check-install
```

Do not set `core.hooksPath` manually. Automated setup may use Lefthook's native `--reset-hooks-path` option to repair old clones.

## Historical incident

Before the migration, this repository used a relative `.githooks` value. PR #2138 and PR #2136 diagnosed a clone with an absolute `core.hooksPath` pointing at an empty hooks directory. Every worktree inherited that shared Git config and silently bypassed the repository guards. The now-deleted `scripts/install_git_hooks.py` installer repaired and checked that legacy configuration.

The historical finding remains useful: local hooks cannot detect that Git never launched them. A required CI check remains the non-bypassable backstop.

**Created**: 2026-05-30

**Superseded**: 2026-07-19

**Category**: Git