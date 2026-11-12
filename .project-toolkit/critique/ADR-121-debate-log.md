# ADR Debate Log: ADR-121 One Resolver Launches Every Shipped Plugin-Root Shell Command

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: none
- **Outcome**: Consensus
- **Final Status**: proposed
- **Panel**: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the change designs executable enforcement: a launcher that every shipped command runs, and the validator that gates it.
- **Owner decision taken before review**: on 2026-11-11 the owner chose option a of issue #7281, "one resolver plus an ADR", over a per-plugin variable name and over document-and-defer. The panel reviewed the design, not that choice.
- **Pre-review architect pass**: one architect pass drafted the first design on 2026-11-11, before the ADR text existed. The panel's architect seat reviewed the written ADR independently.

## Phase 0: Related work

- Issue #7281 (open): the decision this ADR records.
- PR #7318 (merged 2026-11-11, merge 117f6c2f0): the gate-side probe. It is the Class G answer.
- Issue #3897: the Python bootstrap for GitHub skill scripts.
- Issue #7226 and PR #7244: converted about 90 commands to the nested form.
- Issue #7277 and PR #7294, PR #7300: same root cause, merged.
- No open PR implements the resolver.

## Claims ledger

Verified in round 1 by at least two seats each, all at 48b4ea4c2 (2026-11-11):

| Claim | Result |
|---|---|
| 489 authored sites: 287 in 74 files, 50 in 33 files, 2 in 1 file, 150 in 43 files | VERIFIED by critic, architect, analyst, advisor |
| The 150 split as 123 Markdown, 19 YAML, 8 `.py` | VERIFIED by the author's recount, analyst, advisor |
| Gate splits commands with `shlex` and runs no shell | VERIFIED by security, analyst, architect |
| `copilot_launcher.py` takes the first set variable and defines the target pattern | VERIFIED by five seats |
| Rewrite probe rows 3 to 7 (fenced block, agent body, `references/`, `CLAUDE_SKILL_DIR`) | VERIFIED by the author's re-run, independent-thinker, advisor |
| Copilot CLI probe UNAVAILABLE (quota), Codex NOT RUN | VERIFIED as stated |

REFUTED in the first draft: "all targets sit under `skills/*/scripts/`". The security and architect seats found shipped targets such as `skills/metrics/collect_metrics.py`.

## Round 1 Summary

### Key Issues Addressed

Phase 1 findings, by seat. All six returned at least one P0 or P1.

- **architect**: P0, the target allowlist `skills/*/scripts/*.py` would break 141 shipped sites. P1: print the locator, exit 2 collides with a target's exit 2, rule amendments missing from the rollout, rewrite probed only in skill text.
- **critic**: NEEDS_REVISION. P0: rewrite coverage unprobed outside `SKILL.md`. P0: a second install of this plugin passes the marker probe. P1: site shapes (`-I`, `bash -c`, variable assignments), trees without `lib/`, incident-repeat coverage.
- **independent-thinker**: P0, the safety claim "no environment can change the first candidate" fails for `references/`, measured. P1: same-plugin foreign root, exit 2 collision, the per-host-render alternative was not examined.
- **security**: P0, falling back to a PR-writable `.claude` and a gate that cannot expand a shell locator. P1: Windows `os.execv`, quoting, allowlist against ADR-119 symlinks.
- **analyst**: P0, the gate cannot run a shell locator, so decision 8 contradicted decision 9. P0: rewrite evidence covers skill text only. P1: wrong parity precedent, instruction budget.
- **high-level-advisor**: PROCEED with a split. P0: the problem statement understates the failure (consumer-wide `.claude` resolution), migrate the 337 rewritable sites first, make the non-Claude probes a hard step 4 precondition.

Phase 2 consensus points: scope the rewrite claim to measured surfaces; print the locator; keep the gate out of the locator's reach; fix the target pattern; add rule amendments, a budget check, and a review date.

Phase 2 conflict: the advisor wanted the Copilot and Codex probes as a hard gate. The author did not. The locator degrades to today's `.claude` behavior and fails loud, so no host regresses. The ADR records those hosts as unproven. The advisor accepted this in Phase 4.

Review anti-patterns: none flagged. Every seat produced substantive findings and ran its own checks.

### Major Changes Made

- Three site classes. Class S gets the locator. Class G (gate YAML, Python bootstrap) stays on Python resolution from PR #7318. Class P (Copilot `pwsh`) is a follow-up.
- The locator is printed, with measured cost: 260 against 92 characters, 12 ms for a second `python3` start.
- Target pattern matches `copilot_launcher.py`; the check is lexical, with no realpath.
- Off-POSIX runs use `subprocess.run`. Exit 2 carries the `ptk_run:` stderr prefix.
- The evidence table adds fenced blocks, agent bodies, `references/`, and `CLAUDE_SKILL_DIR`, each measured.
- Decision 10 states the resolver does not authenticate a root, and records the second-install and `.claude` cases.
- Rollout adds rule amendments, a budget check, per-tree resolver shipping, and a step 5 for the 152 non-rewritable sites. Frontmatter gains `review-by: 2027-02-11`.
- The per-host-render alternative is recorded with the reason the resolver contains it.

Corrections folded in after the votes, none of which changes the design:

- Count wording: 337 template sites, 238 rendered Claude sites by one panel count (INFERRED).
- Step 3: rule 5 is a per-module scan, so only rules 1 and 2 apply to the extracted target.
- Step 3: audit `allowed-tools` patterns of the form `Bash(python3 ...)` and run a real-CLI permission test before any site migrates (independent-thinker dissent).
- Step 3: the validator rejects the locator in gate-dispatched YAML (security note).
- The quoting matrix gains a host-inlined root with `$`, a backtick, and a double quote.
- Decision 3: the first-candidate guarantee holds when the resolver is present at that path.
- Step 5 gets an owner and a start condition (architect dissent).
- Step 2 checks the smoke job's `continue-on-error` setting (advisor note).

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Disagree-and-Commit | Step 5 holds the sites where the probe is the only protection, so it needs an owner. Other hosts stay unproven. |
| critic | Accept | Both P0s closed. Wording note on decision 3 applied. |
| independent-thinker | Disagree-and-Commit | `allowed-tools` prefix patterns may not match a locator that starts with `( for`. Untested. Added to step 3. |
| security | Accept | Both P0s resolved by Class G and decision 10. Two P2 notes applied. |
| analyst | Accept | Count and rule 5 corrections applied. |
| high-level-advisor | Accept | Probe gate dissent recorded and accepted. |

### Next Steps

Merge the ADR as `proposed`. The resolver pull request (rollout step 2) implements it. The ADR moves to `accepted` when step 2 merges with its tests green.

## Debate State

**Round**: 1 of 10 (counted within this debate log)
**Status**: Consensus

Unresolved P0 issues: none.
