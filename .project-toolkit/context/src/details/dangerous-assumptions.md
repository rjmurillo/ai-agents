## Dangerous assumptions

- `copilot-cli/docs/copilot-instructions.md` looks generated; hand-authored, no byte ratchet (that binds `.github/copilot-instructions.md`).
- `OWNED_PREFIXES` carries a bare `src/`: any uncommitted change here, this file included, reds `build_all.py --check` and pre-PR `Generated Artifact Staleness`. Commit, do not just regenerate.
