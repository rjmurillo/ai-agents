# Post-Incident Report: Plugin Manifest Schema Regression

**Incident ID**: PIR-2026-04-27-001
**Severity**: P0 (customer-impacting, plugin install broken for all consumers)
**Status**: Mitigated (fix in PR #1795, awaiting merge)
**Author**: Richard Murillo (with Claude)
**Date**: 2026-04-27

---

## Summary

PR #1773 (`feat(plugins): add plugin.json manifests for 3 marketplace plugins`, merged 2026-04-26 13:15 PT, commit `645f8689`) introduced explicit `plugin.json` manifests under three plugin source directories. Each manifest declared `agents`, `skills`, `commands`, and `hooks` keys with shapes that violate the Anthropic plugin schema. As a result, every consumer attempting to install or reload the `project-toolkit` plugin received:

> Validation errors: hooks: Invalid input, agents: Invalid input

The two sibling plugins (`claude-agents`, `copilot-cli-agents`) carried the same `agents` defect but lacked the `hooks` block, so their failure mode was the second "2 errors during load" reported by `/reload-plugins`.

## Customer impact

- **Scope**: All consumers of the `ai-agents` marketplace via Claude Code v2.1+ (3 plugins).
- **Effect**: Plugin manifest validation rejected the plugins at load time. Consumers received a hard validation error rather than a degraded-but-functional plugin. Agents, skills, commands, and hooks shipped by the plugins were unavailable.
- **Detection lag**: ~14 hours between merge and external detection. The merge happened during a high-velocity day (30+ PRs to main) and the manifests were not exercised by existing CI.
- **Reporter**: Richard, via `/reload-plugins` output during a routine session.

## Timeline (UTC)

| Time | Event |
|---|---|
| 2026-04-26 20:15 | PR #1773 merged to `main` (commit `645f8689`) |
| 2026-04-26 20:15 to 2026-04-27 ~10:00 | Plugin install silently broken for all consumers (no automated detection) |
| 2026-04-27 ~10:00 | Reporter ran `/reload-plugins`, surfaced "2 errors during load" |
| 2026-04-27 ~10:05 | Triage: read `~/.claude/plugins/cache/ai-agents/project-toolkit/.claude-plugin/plugin.json`, confirmed invalid `hooks` and `agents` shapes |
| 2026-04-27 ~10:10 | Compared against working plugin (`caveman`) to confirm correct schema |
| 2026-04-27 ~10:15 | Consulted Claude Code plugin docs via `claude-code-guide` agent for authoritative schema |
| 2026-04-27 ~10:25 | Wrote validator `build/scripts/validate_plugin_manifests.py` + 20 pytest tests |
| 2026-04-27 ~10:35 | Created composite action `.github/actions/validate-plugin-manifests/` and workflow `.github/workflows/validate-plugin-manifests.yml` |
| 2026-04-27 ~10:45 | Stripped invalid keys from all 3 manifests; ported `.claude/settings.json` hooks to `.claude/hooks/hooks.json` so consumers receive the hooks the repo uses internally |
| 2026-04-27 ~11:00 | All 20 tests pass; validator green on all 3 manifests; opened PR #1795 |

## Root cause

PR #1773's commit message states the intent: "Add explicit plugin.json manifests under each plugin's source dir so both Claude Code and Copilot CLI can discover and expose plugin components (agents, skills, commands, hooks) without inferring from directory layout."

The intent was valid; the execution violated the schema:

1. **`hooks` declared as a dict-of-directories**:
   ```json
   "hooks": {
     "PreToolUse": "./hooks/PreToolUse",
     "PostToolUse": "./hooks/PostToolUse",
     ...
   }
   ```
   Anthropic schema requires either inline matcher-group objects (`{ EventName: [{ matcher, hooks: [{type, command}] }] }`) or a string ref to a single `*.json` file. Pointing at a directory of Python scripts was never supported.

2. **`agents`/`skills`/`commands` declared as arrays of directory paths** (`["./agents"]`, `["./"]`):
   Anthropic schema treats these as optional. When omitted, Claude Code v2.1+ auto-discovers from the default `./agents/`, `./skills/`, `./commands/` directories. The array-of-dirs shape used here was rejected as "Invalid input".

The failure mode was deterministic and reproducible on every install. It was not surfaced by any existing CI because no test exercised plugin schema conformance.

### Five Whys

1. **Why did plugin install fail?** Manifest schema invalid.
2. **Why was the schema invalid?** Hooks declared as dict-of-directories; agents declared as array of dir paths.
3. **Why were these shapes used?** Author inferred the schema rather than verifying against documented examples or live plugins.
4. **Why was inference accepted?** No CI gate existed for plugin manifest conformance.
5. **Why no CI gate?** Plugin manifests were a new artifact class added in the same PR; gating did not exist before they did.

The terminal cause is **gap in CI coverage for a new artifact class**. The proximate cause is **schema inference without verification**.

## What went well

- Detection happened during a normal session (no production-style outage paging needed).
- A working plugin (`caveman`) existed in the local cache as a reference implementation.
- The `claude-code-guide` agent provided authoritative schema citations within minutes.
- The fix is local to 3 files plus a hooks port; no architectural change required.
- Atomic commits per AGENTS.md kept the PR reviewable.

## What went poorly

- **No CI gate for plugin manifests existed** at the time PR #1773 introduced them. The manifest format went straight from author keyboard to consumer install with zero deterministic verification.
- **30+ PRs landed to main on 2026-04-26**. Velocity was high; review attention was diffuse.
- **Detection took 14 hours**. This is not a real production-monitoring metric (no telemetry on plugin install failures), but it is the upper bound on how long a customer-broken state can persist undetected.
- **Manifest counts in description were validated** (`validate_marketplace_counts.py`) but **manifest schema was not**. Counts are a derived property; schema is the load-bearing contract.
- **Author of #1773 (rjmurillo-bot, AI agent) was not gated by a schema check**. The PR's review process trusted the agent's output.

## Remediation

### Shipped in PR #1795

- `build/scripts/validate_plugin_manifests.py`: deterministic schema check with 20 unit tests.
- `.github/actions/validate-plugin-manifests/action.yml`: reusable composite action.
- `.github/workflows/validate-plugin-manifests.yml`: CI gate triggered by changes to any `plugin.json`, `hooks.json`, the validator, or its tests.
- All 3 plugin manifests fixed.
- `.claude/hooks/hooks.json` created with inline matcher format (ported from `.claude/settings.json`) so plugin consumers receive the same hooks the repo uses internally. Paths use `${CLAUDE_PLUGIN_ROOT}` for portability.

### Follow-ups (separate work)

1. **Investigate why review didn't catch the schema bug**. PR #1773 has multiple bot co-authors; the human review surface was thin. Consider requiring at least one human reviewer on PRs that introduce a new artifact class.
2. **Inventory other "new artifact class" gaps**. Search for repo additions in the last 30 days that are not gated by schema validation. Likely candidates: `marketplace.json` plugin entries, agent frontmatter, skill SKILL.md frontmatter.
3. **Add a smoke test that loads each plugin** (not just validates the manifest). A passing schema check is necessary but not sufficient — the validator can drift from the live Claude Code parser.
4. **Document the canonical plugin.json shape** in the repo. Right now the only authoritative reference is upstream Anthropic docs and the `caveman` example in `~/.claude/plugins/cache/`.
5. **Backstop with an inverted regression test**: a test that constructs the exact PR #1773 manifest shape and asserts the validator rejects it. (Already shipped: `test_regression_hooks_as_dict_of_strings_rejected`.)

### Process

- **Schema gates for new artifact classes** must be opened in the same PR that introduces the artifact. PR #1773 should have included `validate_plugin_manifests.py` from day one.
- **High-velocity days** (>10 PRs/day to main) should trip a velocity-aware reviewer rotation. Right now a 30-PR day looks the same as a 3-PR day to the gating system.
- **Automated post-merge smoke tests** for plugin install would convert "14-hour detection" into "minutes-after-merge detection". Out of scope for this PIR; logging for future quarter.

## Verification

```text
$ python3 build/scripts/validate_plugin_manifests.py
OK   .claude/.claude-plugin/plugin.json
OK   src/claude/.claude-plugin/plugin.json
OK   src/copilot-cli/.claude-plugin/plugin.json

All 3 manifest(s) valid

$ uv run python -m pytest tests/build_scripts/test_validate_plugin_manifests.py
============================== 20 passed in 1.37s ==============================
```

Post-merge verification (manual): run `/reload-plugins`, expect zero "Invalid input" errors. Open follow-up issue if any consumer still reports the failure.

## Lessons

1. **Inferring schemas from neighboring fields is a class of bug that cannot be code-reviewed reliably**. The only reliable defense is a deterministic check against the actual schema.
2. **A new artifact class without a schema gate is a regression in latent form**. The bug was always going to happen; the question was when, not if.
3. **Auto-discovery is the safest default**. The PR #1773 author added explicit declarations to be helpful. The schema rejected them. Working plugins (caveman) omit them. Helpful is not always correct.
4. **High velocity erodes review quality**. 30 PRs/day means the median PR gets reviewed by an exhausted human or an unaccountable bot. The fix is not "review harder", it is "make the gates deterministic so review-as-safety-net is unnecessary".

## References

- Regressed by: PR #1773 (commit `645f8689`)
- Fixed by: PR #1795 (`fix/plugin-manifest-schema-1793`)
- Session log: `.agents/sessions/2026-04-27-session-1759-fix-plugin-manifest-schema-regression.json`
- Anthropic plugin docs: https://code.claude.com/docs/en/plugins-reference
- Reference plugin: `~/.claude/plugins/cache/caveman/caveman/.claude-plugin/plugin.json`
