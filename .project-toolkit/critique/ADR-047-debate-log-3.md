# ADR-047 Debate Log 3: amendment wording fixes from PR #7536 review

Prior debate log: `.project-toolkit/critique/ADR-047-debate-log-2.md` (closed, consensus).
Claims ledger: `.project-toolkit/critique/ADR-047-claims-ledger.md`.
Scope: two prose corrections Devin raised on PR #7536. No enforcement code changes.
Panel: reduced (architect and critic).

## Round 1

### Changes under review

1. The 2026-11-24 amendment's "Test impact" paragraph said the bootstrap test "runs every copy". It now says the test runs every authored copy under `src/claude/skills/` and `.claude/skills/`. It also says all 77 generated copies are byte-identical to their sources, and that `build_all.py --check` keeps every generated tree in sync.
2. "Checklist for New Hooks" item 1 prescribed the standard boilerplate for every script. It now names the amendment's shape for skill scripts that import `hook_utilities.frontmatter_block`.

| Agent | Position |
|-------|----------|
| architect | Accept. Nit: name the hermes copies. Applied |
| critic | Disagree-and-Commit: the count omitted 13 hermes copies. Applied |

### Evidence

- `cmp` of each of the 18 authored scripts against every generated mirror: 16 copies each in copilot-cli, codex, cursor, and muse, plus 13 in the hermes packs, for 77 total. None differ (2026-11-24 UTC).
- `tests/test_frontmatter_bootstrap_foreign_root.py` lists only `src/claude/skills/*.py` and `.claude/skills/*.py`.

## Outcome

Consensus: Accept (2 of 2) after the hermes count was added. Status unchanged: `accepted`, `implemented: true`.
