# Retrospective: An installed plugin enforced guards deleted from main, and no session surface said so

## Session Info

- **Date**: 2026-09-01
- **Agents**: Claude Opus 5 (1M context), implementer role, single isolated worktree
- **Task Type**: Bug
- **Outcome**: Partial (one of the issue's four asks closed; two need consumer-side discovery)
- **Failure Mode**: None of the eleven in `.agents/governance/FAILURE-MODES.md`
  fits. An earlier draft claimed Class 11, which is wrong. Class 11 is a
  generated artifact that ships behaviorally broken because no gate ever ran it
  under its target host's runtime contract (lines 404 to 425). This artifact
  executed correctly when it was built and went on executing correctly. The
  defect is that it stayed installed and kept enforcing a policy retired
  upstream: a freshness and invalidation gap, not an unexecuted runtime
  contract. ADR-097 retired the guards and specifies no invalidation step for
  copies already installed (searched `ADR-097-zero-tool-use-hooks.md` for
  invalidation, uninstall, installed copy, and stale install; no match). Asks 1
  and 2 of issue #5085 own that open question. Class 9,
  confident-incorrectness recurrence, is a real compounding factor and stands.

## Evidence

- Issue: <https://github.com/rjmurillo/ai-agents/issues/5085>, measured 2026-08-15
- Guard removals the install did not receive: ADR-062 amendment (issue #3214),
  PR #3293, commit `14d7ce1a4` in PR #3240
- The self-host bail that gate groups deliberately bypass:
  `.claude/hooks/invoke_dispatch_claude.py` lines 173 to 184, added by
  `5cd72a7da` (PR #4825, Fixes #4764)
- The shipped state the install contradicts: `.claude/hooks/hooks.json` carries
  `"hooks": {}` since `f79e70c01` (ADR-097, PR #5172); `tests/hooks/test_zero_tool_use_hooks.py`
  is the ratchet that holds it there
- The named stale-copy locations: `.claude/rules/ci-scripts.md` MUST 8, which
  calls `~/.claude/plugins/cache` and `~/.copilot/installed-plugins` copies that
  "can be arbitrarily old"

## Phase 1: Root Cause

The reported session lost roughly 45 minutes, filed and closed issue #5075, and
renamed a QA report to escape a gate that no longer exists. The five whys:

1. Why was the delegation blocked? A PreToolUse guard denied it.
2. Why did a guard deny it, when `origin/main` contains no such guard? The guard
   came from an installed plugin copy, not from the checkout.
3. Why did the installed copy still carry it? Its content lags `main`. The
   freshness-resolution mechanism (ADR-092: no manifest `version`, resolve from
   the source commit SHA) either did not apply or did not fire. Unverified; it
   depends on the consumer's plugin cache and CLI version, neither of which is
   in this repository.
4. Why did the guard run at all inside the publishing repo, where
   `.claude/settings.json` is the authority? The dispatcher's self-host bail is
   scoped to non-gate modes on purpose, so a stale install's `gate` groups run
   even there.
5. Why did diagnosis cost 45 minutes? Nothing in the session compared the
   install against the checkout. A stale worktree at `.wt/workspace` still held
   the deleted script with matching line numbers, so the evidence available
   pointed at live code. That is the Class 9 shape: partial signal, premature
   conclusion, confident delivery.

The root cause of the diagnostic cost, as distinct from the staleness itself, is
that **the install and the checkout were never compared**. Two independent
sources of truth existed on one disk and nothing read both.

## Phase 2: What Was Done

Added `.claude/hooks/SessionStart/invoke_plugin_hook_drift_check.py`, an observe
mode, fail-open SessionStart hook that reads the hook registrations in both
shipped plugin manifests in the checkout and compares them against every
installed copy of the same plugin found under `~/.claude/plugins` and
`~/.copilot/installed-plugins`, then names the registrations present in an
install but absent from source. Post ADR-097 any `PreToolUse` entry in an
install is drift by definition, so the report is specific: which file, which
event, which install path.

Verified by four independent mutations, each reverted after measurement:

| Mutation | Tests that failed |
|---|---|
| Stop reporting registrations only in the install | 3, including the issue-shape test |
| Stop reporting registrations only in the source | 1 |
| Read an unreadable manifest as an empty set | 3 |
| Follow symlinks and drop directory pruning | 2 |

## Phase 3: What Was Deliberately Not Done

**The gate-mode carve-out stands.** Making the self-host bail apply to `gate`
groups would stop a stale install from enforcing retired policy inside the
publishing repo, which is the sharpest available fix for the reported symptom.
It is also a security change: PR #4825 made gates non-bypassable by a self-host
claim on purpose, and a bail there means a real guard can be silenced by a
plugin manifest that merely claims to be self-hosted. That is an Ask First
decision under `AGENTS.md` and needs its own review, not a drive-by.

**The consumer case is not closed and the hook says so in its own docstring.**
A consumer with a stale install never receives this hook, because the stale
install is what would have to ship it. Nothing shipped in an artifact can
detect that the artifact is stale unless something outside it looks. Asks 1 and
2 of the issue (why freshness resolution did not apply, and how a consumer
learns) remain open and need evidence from a real install, not from this repo.

**Ask 3, cleanup, is not code.** The stale trees named in the issue are on the
reporter's machine.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Contributor diagnosis time | High | 45 minutes on one occurrence; the class recurs silently |
| Artifact correctness | Medium | A QA report renamed on PR #5062 to escape a gate that does not exist |
| Consumer trust | High (unmeasured) | The issue names this as a plausible uninstall mechanism; no install telemetry exists to confirm |

## Remediation

| Action | Owner | Tracking |
|---|---|---|
| SessionStart drift check comparing installs against the checkout | this change | Refs #5085 |
| Determine why freshness resolution did not invalidate the stale install | needs a real install to probe | #5085 ask 1 |
| Decide whether removing a hook should actively invalidate installed copies | architecture, Ask First | #5085 ask 2 |
| Extend the drift check to the consumer case, which requires an out-of-band signal | blocked on ask 2 | #5085 ask 4 follow-up |

Not a remediation row: `_drain_stdin` and `_emit_utf8` are now duplicated across
four SessionStart and PreCompact hooks and want factoring into `hook_utilities`.
An earlier draft listed this with owner "unassigned" and tracking "new issue",
which is neither an owner nor a link. It is recorded here as an observation
until someone opens the issue; a remediation row with no tracking reads as
planned work that nobody is doing.

## Learnings

1. **A shipped artifact cannot verify its own freshness.** Any self-check written
   inside the plugin is only as current as the plugin. The comparison has to
   come from a second, independently updated source. Here that source is the
   maintainer's checkout, which bounds who the check can help; that bound is
   documented rather than papered over.
2. **Report both directions of a divergence.** An install missing a hook the
   source ships is half-updated. A check that reports only the extras would
   certify that state as clean, which is the same silent-pass failure the
   check exists to prevent.
3. **A malformed manifest and an empty one are opposite verdicts.**
   `scripts/ci/test_installed_plugin_hooks.py` already learned this under
   ADR-097 and split `_registered_events` from `_manifest_is_readable`. The new
   hook follows that split rather than reinventing the collapse.
4. **Matching line numbers are not provenance.** The reported session attributed
   behavior to live code because a stale worktree carried the pre-removal
   revision exactly. Confirm the file that ran, not a file that looks like it.
