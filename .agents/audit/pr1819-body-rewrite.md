## Summary

REQ-003 multi-tool artifact build system. Started as the M0 doc-only ADR-006 amendment gate; now spans the full implementation through M7 vendor-install hardening.

The build pipeline reads canonical authoring under the `.claude/` directory and emits native artifacts for the Copilot CLI plugin (and the marketplace registry that surfaces it). Single source of truth for agents, skills, commands, rules, hooks, and the supporting library package.

## Milestones shipped

- **M0** — ADR-006 amended with a config-data exception gated by 7 conditions and 6/6 multi-agent consensus.
- **M1** — Schema foundation: a copilot-cli platform yaml in templates/platforms and a templates schema validator under build/scripts.
- **M2** — Counter generalization: a marketplace-counters yaml in templates and a refactored marketplace-counts validator.
- **M3** — Low-transform generators for agents, skills, and rules under build/scripts.
- **M4** — Medium-transform generators: a commands-to-skills bridge and the rules vendor-install path filter.
- **M5** — Hook generator with matcher shim, per-matcher SHA-suffixed filenames, snake_case wire format consumed by the shim.
- **M6** — Marketplace two-plugin model: claude-toolkit and copilot-cli-toolkit entries added to the marketplace registry alongside the legacy entries.
- **M7** — Vendor install hardening: lib generation step in the build orchestrator, plugin-manifest walk-up bootstrap in 23 source hooks, CWE-22 containment guards, URL scheme allowlist, git verb allowlist, privacy and timeout defaults.

## Test surface

Roughly 1500 tests under tests/build_scripts/, tests/skills/, tests/hooks/, and tests/test_hook_utilities.py. New tests cover: future-import hoist, snake_case wire format, the lib copy step, vendor-install glob filter warning emission, the run_git allowlist, URL scheme validation, the plugin-manifest walk-up bootstrap, and the multi-matcher session-log gate.

## Plan and spec artifacts

The plan and spec live under .agents/plans/active/ and .agents/specs/requirements/. The ADR amendment is .agents/architecture/ADR-006-thin-workflows-testable-modules.md (Round 1, 2, and 3 amendments).

## Breaking changes

- The skill-learning LLM fallback is now opt-in. Operators who want it must set the explicit env flag.
- get_api_key no longer scans .env files. Operators provide credentials via the environment.
- The session-log guard now blocks pr-creation commands without a session log. Pre-fix the guard silently no-opped for that matcher.
- Generated instruction files may have lost glob entries that pointed at internal-only repo paths. The build emits a warning per dropped entry.

## Verification

- `uv run pytest` passes locally across the test directories listed above.
- `python3 build/scripts/build_all.py --check` reports clean.
- The marketplace counts validator reports counts match.
- The plugin-manifest walk-up bootstrap is verified by direct shimmed-hook invocation: hook_utilities now imports successfully.

## Test plan

- [x] Spec EARS-formatted with testable acceptance criteria.
- [x] Plan tasks each have explicit acceptance criteria.
- [x] ADR amendment passes multi-agent debate.
- [x] All milestones M0 through M7 have verifying tests.
- [ ] CI green on this PR.
- [ ] Reviewer approval.

## Related

- Aftermath of PR #1773 regression and PR #1795 P0 fix.
- Successor PR #1829 (markdownlint config performance) merged to main and pulled into this branch via merge commit.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
