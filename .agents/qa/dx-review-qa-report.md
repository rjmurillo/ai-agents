---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14705.json
qaCommit: 5ff9c23f25eab9b83c5bea568c03578abc73fd1c
---

# QA Report: dx-review skill and attribution

Branch: `feat/dx-review`
Commit: `5ff9c23f25eab9b83c5bea568c03578abc73fd1c`

## Files in scope

- `.claude/skills/dx-review/SKILL.md` (canonical)
- `src/copilot-cli/skills/dx-review/SKILL.md` (generated)
- `tests/skills/dx-review/test_dx_review_contracts.py`
- `scripts/generate_third_party_notices.py`
- `tests/test_generate_third_party_notices.py`
- `THIRD-PARTY-NOTICES.TXT`

## Check results

| # | Check | Command / method | Result |
|---|-------|------------------|--------|
| 1 | pytest | `uv run pytest tests/skills/dx-review tests/test_generate_third_party_notices.py -q` | 32 passed, 0 failed |
| 2 | Ruff | `uv run ruff check scripts/generate_third_party_notices.py tests/skills/dx-review tests/test_generate_third_party_notices.py` | All checks passed |
| 3 | SkillForge quick | `uv run python scripts/validate_skill_format.py --path .claude/skills/dx-review` | PASSED |
| 4 | SkillForge full | `uv run python scripts/validate_skill_installation.py --verbose` | PASSED (100 skills, dx-review OK) |
| 5 | Docs safety | `uv run python scripts/detect_skill_violation.py --file .claude/skills/dx-review/SKILL.md` | No violations |
| 6 | Canonical vs generated match | Byte comparison | Identical (9,138 bytes) |
| 7 | Notice generator | `uv run python scripts/generate_third_party_notices.py --check` | Current |
| 8 | Command safety | Manual inspection of SKILL.md | Present: "Shell commands are not pre-approved"; "Every command...requires explicit user approval via AskUserQuestion"; Bash absent from allowed-tools |
| 9 | Evidence labels | Manual inspection | TESTED, PARTIAL, INFERRED table with definitions present |
| 10 | Conditional TTHW | Manual inspection | "only when the target supports a runnable example"; "Never hardcode TESTED for TTHW"; scorecard uses `[actual/N/A]` |
| 11 | Browser fallback | Manual inspection | "use browser tooling...when available. Fall back to web fetch or artifact inspection with PARTIAL or INFERRED evidence when browser tooling is unavailable" |
| 12 | Triggers | Manual inspection | 5 trigger phrases mapped in table |
| 13 | MIT attribution | Exact license comparison | Full gstack MIT text and paragraph breaks match the pinned license |
| 14 | Existing notice stability | Byte comparison to HEAD | SkillForge notice block unchanged |
| 15 | Skill provenance removal | Contract test and manual inspection | No gstack source or adaptation prose remains in the skill |
| 16 | Em/en dash check | Regex scan of authored changes | None found |

## Verdict

All 16 checks pass. No blockers.
