# Adding a file to a shipped skill can break the Hermes pack budget

## What happens

Each Hermes pack under `src/hermes/` has a file budget, `packMaxFiles`, in `templates/platforms/hermes.yaml`.
The count includes the pack's `lib/` files and `plugin.json`.
`check_pack_limits` in `build/scripts/hermes_pack_checks.py` fails the build when a pack goes over.
So a new script, reference, or test fixture inside a shipped skill can fail the build.
The failing check names the pack, not your file.

Hermes itself refuses a pack over 400 files (`HERMES_MAX_PACK_FILES`, `build/scripts/hermes_pack_config.py` line 25).
The config loader rejects a `packMaxFiles` above 400.

## Current numbers

- [2026-11-16] at `2e98e526a`: `packMaxFiles` is 381.
- `project-toolkit-knowledge` holds 381 files, so it has no room left.
- `project-toolkit-delivery` holds 352 files.

## Options when a pack is full

- Fold the new file into an existing module in the same skill.
- Raise `packMaxFiles`, up to 400. That edit is user-visible scope, so ask first.
- Move a skill to the other pack. `hermes_pack_checks` requires skills that link to each other to share a pack.

ADR-115 Decision 6 points to `packMaxFiles` and does not restate the number. Do not copy the number into prose.

## Evidence

- [2026-11-16] [orchestrator session, PR #7387]: Splitting `conformance.py` added `_conformance_judging.py` to skillforge. The knowledge pack hit 381 against a budget of 380. The user chose to raise the budget to 381.

## Relations

- **related_to**: [ci/ci-count-ratchet-never-names-the-offending-file](ci-count-ratchet-never-names-the-offending-file.md)
