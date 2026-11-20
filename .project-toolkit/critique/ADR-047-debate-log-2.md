# ADR-047 Debate Log: Shared Skill Paths Bootstrap

## Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-047-plugin-mode-hook-behavior.md |
| Date | 2026-11-19 |
| Prior debate log | [Original debate](ADR-047-debate-log.md) |
| Round | 1 of 10 |
| Status | Consensus |
| Outcome | Accept the bounded amendment |
| Open blockers | P0: 0. P1: 0. |

## Scope

The owner approved sharing the bootstrap for two existing skill entry points.
Only `council.py` and `sol_loop.py` receive the inline-bootstrap exception.
The existing build ships `scripts/hook_utilities/bootstrap.py` as `lib/bootstrap.py`.
No shipped file, caller, hook behavior, privacy contract, or quota changes.
No baseline, gate, allowlist, suppression, or threshold changes.

The reviewed base was `6f4358628`.
The canonical review patch had this SHA-256:

```text
a100b19fd76d09501ab0c4ccea3fbaf9670f39dce19347cce1fa4357d3b495f6
```

Six independent Factory delegates reviewed that patch and the regression tests.
This panel did not use the fourteen reserved final-review slots.
Five delegate calls timed out while their child reviews continued.
Their completed reports were recovered without starting replacement reviewers.

## Prior Spike Findings

The earlier spike validated `paths.py`, then imported `paths` by name.
Cached modules and packages could replace the validated file.
Isolated entry-file symlinks also broke sibling imports.
The earlier panel blocked that spike.
It also identified ambient `pkgutil` loading through the `runpy` bootstrap.

The recovered implementation uses explicit file loaders for both bundled modules.
It loads the selected `paths.py` without consulting module caches.
It places the resolved entry directory first for sibling imports.
Copilot, Claude, and own-library precedence remains unchanged.
Ordered candidate exhaustion still raises `RuntimeError`.

## Agent Positions

| Agent | Vote | Evidence and limitations |
|-------|------|--------------------------|
| architect | Accept | Ran 60 focused tests. Verified exact-file loading and mirror identity. |
| critic | Disagree-and-Commit | Passed 28 isolated source launches and poisoned-module probes. Installed fixtures were inspected. |
| independent-thinker | Disagree-and-Commit | Independently passed 52 regression tests and ambient-import traps. |
| security | Disagree-and-Commit | Passed 28 fresh-process launches and poisoned-cache probes. Verified unchanged hook ASTs. |
| analyst | Disagree-and-Commit | Passed 28 launches and inspected precedence, exhaustion, and resolved-directory behavior. |
| high-level-advisor | Disagree-and-Commit | Passed 28 isolated launches. Verified pack counts, library counts, and skill totals. |

All six reported zero unresolved P0 and P1 findings.
The architect disclosed a temporary probe outside the requested scratch directory.
That reviewer reported deleting it. The implementation worker did not reproduce that write.
Other reviewers reported no repository changes.

## Findings and Resolution

### P2: Clarify the helper exception

All six reviewers found ambiguous wording in the shared module's docstring.
It appeared to permit the two entries to call `setup_hook_lib_path()`.
The approved exception permits `load_skill_paths()` instead.
The worker applied the reviewers' exact distinction and regenerated every mirror.
This post-review clarification changed only the docstring, not executable statements.
The ADR text and tested behavior remain the reviewed versions.

### P2: Optional Review Date

The architect recommended adding a review date to the amendment.
The panel accepted the decision without making that recommendation blocking.
The amendment remains bounded to two named callers.
Any additional caller requires another architectural decision.
No extra ADR edit was made for this optional suggestion.

## Verification

The implementation worker reran the final source and generated artifacts.

- Feature, layout, hook compatibility, library, and pack tests: 600 passed.
- Existing ADR evidence-policy tests: 73 passed.
- Ruff checks and formatting passed.
- ADR links passed across 4461 tracked Markdown files.
- All three existing hook-helper function ASTs remained unchanged.
- The new regression module contains 242 lines.
- Independent spike comparison reproduced both original failures.
- Fixed copies rejected cached-module bypass and passed both isolated entry-file links.
- The duplication scan reported zero council/sol-loop entry-point clones.
- Duplication gate exited 1 for 30 stale entries, with no growth.
- Baseline pruning remains parent-owned.

Hermes files remain 189, 298, 256, and 163 across four packs.
Each pack contains 55 library files. The packs contain 96 skills total.
The existing 399-file budget remains unchanged.

Full pre-PR validation exited 1.
It reported stale duplication entries and inherited reverse-citation failures.
Generated staleness requires the source and mirrors to be committed together.
The documentation-accuracy check also timed out after 300 seconds.
These results do not authorize broader edits or weakened gates.

## Consensus Decision

One Accept and five Disagree-and-Commit votes close this debate.
No P0 or P1 finding remains open.
The helper-docstring finding is resolved.
The optional review-date suggestion remains nonblocking.
The implementation adds no shipped library or skill file.
