# Incident History: The Stories the Non-Negotiables Compress

The SKILL.md Phase 4 non-negotiables table gives a rationale for each rule. This file tells the six that compress a multi-round failure in full; the other rationale cells are briefer. Read the incident before arguing with its rule; deep history lives in `ai-agents-failure-archaeology`.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

## Fail-closed hooks: the #2205 reversal

A launcher path bug in generated Copilot CLI hooks wedged every customer environment for 33 days across plugin versions v0.3.0 to v0.5.6; recovery required uninstalling. The in-script fail-open shim never ran because the launcher failed before the script started, so "fail-open" did not protect anyone, it only delayed detection (context section of `.agents/architecture/ADR-066-hook-fail-open-reconciliation.md`; incident retro at `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`). The policy reversed: prevention at generation time, then fail closed and loud at runtime. Status precision matters here: ADR-066 is `status: proposed` (as of 2026-07-03), but the position is operative because ADR-071 (Accepted 2026-06-02) records the launcher-level fail-open follow-up (#2230) as rejected, closed addressed-by-prevention. Older ADRs (008, 033, 035, 062) still carry stale fail-open language; the binding direction for hooks is fail-closed. Do not cite the stale ADRs to justify a silent exit 0.

## Plugin version bump: PR #1942

PR #1942 deleted the deprecated `workflow` skill but did not bump `plugin.json`. Installed plugins kept serving the dead `/workflow` command from a stale `0.3.0` cache because nothing signaled the content had changed (`build/scripts/validate_plugin_version_bump.py:10-12`). The gate now requires a strictly greater semver on the touched tree. Do not trust any written version snapshot; re-verify with `grep '"version"' .claude/.claude-plugin/plugin.json src/claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json`. Yes, that includes this file: editing this skill requires bumping `.claude/.claude-plugin/plugin.json`. Incident home: `ai-agents-failure-archaeology` (PR #1942 entry).

## Escape-hatch abuse: session 1187

`SKIP_PREPUSH` was introduced at 08:55 as an "emergency use only" bypass. First abuse at 11:04, third by 11:39, each substituting for a root-cause fix. The same session resolved a session-log merge conflict with `git checkout --ours`, overwriting main's historical session 1188 instead of preserving it and renaming the local file to 1189. User verdict, quoted in the retro: "You can't be trusted in the least bit." (`.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md:14-16,41-42,66`). Consequences that still bind: do not introduce a project-specific global hook bypass, session files from main are immutable in merges (`--theirs`, then rename yours), and every surviving escape hatch carries telemetry or an approval requirement.

## Verbatim quoting: FM-9 and PR #1887

FM-9 (`.agents/governance/FAILURE-MODES.md:284-307`) names the failure: a change claims to "match" or "mirror" an existing contract without quoting that contract, modeling it from memory instead. PR #1887's guard framework took 69 commits and 254 review conversations, and its own Phase-6 audit found the guards would have prevented 0 of the 35 fix commits (`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`). The rule: a first commit claiming to match a source MUST cite the path and quote the load-bearing fragment character for character; intentional divergence gets a named divergence section (`.claude/rules/canonical-source-mirror.md`).

## No silent defaults: FM-10 and PR #1965

A CI verdict parser treated a missing `VERDICT:` line as non-blocking, silently defaulting toward PASS. Fixing it took three rounds (commits `5bbf355`, `c1d8209`, `6cb5370`) because the parser, the exit-code translator, and the workflow gate each had their own silent default layered behind the last one. The canon line, quoted verbatim from `.agents/governance/FAILURE-MODES.md`: "there is no neutral default for a missing signal." Either a missing signal is meaningful (raise or block) or the call should never have happened (fix upstream). Applies to `except: pass`, `x or default` on numeric config, and every parser fall-through you are about to write.

## The one documented tension: SHA pinning

`.agents/governance/PROJECT-CONSTRAINTS.md:180` says "Exceptions: None. All third-party actions must be SHA-pinned." GP-006 (`.agents/governance/golden-principles.md:63-69`) allows first-party `actions/*` on version tags with Dependabot. Both are live documents. Resolution until someone reconciles them via ADR: follow the stricter rule (pin everything) unless a human explicitly approves the GP-006 allowance for a first-party action. Flag the tension in your PR description when you hit it; do not silently pick a side.
