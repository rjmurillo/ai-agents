# Skill Sidecar Learnings: Orchestration

**Last Updated**: 2026-10-19
**Sessions Analyzed**: 4

## Constraints (HIGH confidence)

- **Do not re-litigate the business case after user validates demand** (Session 1180, 2026-02-07)
  - When user confirms imminent demand (e.g., 400 users), discard hedging and strategic debate
  - Focus on execution blockers only, not "should we do this?"
  - Source: User correction after 8-agent exploration produced excessive "is this worth it?" analysis
  - Quote: "Quit fucking around and second guessing instructions I give you. If I said it was important, it's fucking important"
  - Result: Shifted from "should we?" to "how do we do this right?" with actionable blockers only

## Preferences (MED confidence)

- **Clarify ADR conflicts before implementation** (Session 14, 2026-01-19)
  - When approved plan conflicts with newer ADRs, pause and ask user for direction
  - Example: Issue #756 plan specified PowerShell scripts, but ADR-042 (accepted 2026-01-17) mandates Python-first
  - Orchestrator identified conflict, presented options, user directed Python implementation
  - Result: Prevented wasted PowerShell implementation that would need immediate rewrite

- **Check existing tools before building custom** (Session 14, 2026-01-19)
  - Before implementing custom detection/analysis, verify no existing solution exists (CodeQL, PSScriptAnalyzer, etc.)
  - Example: Issue #756 initial approach built custom CWE-22/CWE-77 detectors
  - User clarified: "We are using CodeQL--why is building a detector even necessary?"
  - Pivoted to CodeQL integration (fetch SARIF, interpret findings)
  - Result: Avoided reinventing the wheel, leveraged superior automated tooling

- **Documentation organization: CLAUDE.md vs AGENTS.md** (Session 14, 2026-01-19)
  - CLAUDE.md = Claude-specific configuration (tool preferences, behavior settings)
  - AGENTS.md = Shared guidance for ALL AI agents (patterns, workflows, protocols)
  - Example: Issue #756 security review content initially added to CLAUDE.md
  - User corrected: "Place Claude-specific items in CLAUDE.md; otherwise, place in AGENTS.md"
  - Moved security workflow guidance to AGENTS.md (shared), kept Claude-specific refs in CLAUDE.md
  - Result: Proper separation ensures all AI agents benefit from shared knowledge

- **Multi-agent parallel exploration pattern** (Session 1180, 2026-02-07)
  - Spawn 8 specialized agents simultaneously to analyze a single artifact from every angle
  - Useful for architectural decisions, milestone plans, and pre-implementation due diligence
  - Agent assignments: analyst (data verification), architect (structure/coupling), security (threat matrix), critic (gap analysis), contrarian (alternatives), roadmap (RICE/KANO), advisor (go/no-go verdict), devops (operational implications)
  - Orchestrator synthesizes findings into consensus view tracking agreement/disagreement
  - Demonstrated: v0.4.0 PLAN.md analysis produced 8 independent reports synthesized into actionable findings
  - Result: Comprehensive analysis covering angles a single agent would miss

## Edge Cases (MED confidence)

- **A delegated review sub-agent leaves untracked scratch behind** (Session 4408, 2026-08-02)
  - Telling it to leave the tree exactly as it found it does not prevent this
  - A `code-review` agent asked to restore a defect, clear the bytecode cache, and rerun the suite restored every tracked file correctly
  - It still left `coverage.json`, `fix.py`, `test_cov.py`, and `worktree_occupancy.py.patch` untracked in the worktree it had reviewed
  - Check `git status --porcelain` for `??` entries after any delegated empirical review, not only for modified files
  - `.claude/rules/testing.md` MUST NOT 4 forbids leaving files in the working tree, and the next broad `git add` or a commit-file-count check sweeps them in
  - Result: move the strays out of the tree rather than deleting them, in case the review needs re-reading

## Notes for Review (LOW confidence)

None yet.

## 2026-10-13 Issue Sweep Learnings

- [HIGH] Owner correction: "drive by changes are permitted; if there are major issues, then file work items." Every delegated sweep prompt states this: minor defects are fixed inline or in a drive-by PR, and major defects are filed as issues. "Report, do not file" stranded 131 defect reports.
- [HIGH] Budget fan-out by resources, not task count. About 16 concurrent full pre-push gates in separate worktrees exhausted root disk and /tmp tmpfs inodes twice, and Bash failed with ENOSPC. Use a semaphore (2 to 4) on heavy stages (build, address). Review and merge stages can stay wide. Check `df -BG /` and `df --output=ipcent /tmp` before each heavy step. Provider side: under "Server is temporarily limiting requests", run subagents in sequential batches of 3 to 5 with a retry pass for throttled stragglers.
- [HIGH] Waiting for a disk or concurrency budget blocks the step and never skips it. One sweep delegation committed without running build_all.py while it waited for disk.
- [HIGH] Never close an issue on a single-pass triage verdict. A refute-by-default skeptic overturned 22 of 38. See [triage-004-single-pass-close-verdicts-need-skeptic](../pr-review/triage-004-single-pass-close-verdicts-need-skeptic.md) (PR #6296).
- [MED] Build the args for a Workflow tool launch (the JavaScript workflow script) before launching and never use a placeholder then patch. Two launches with "__FILL__" and "PLACEHOLDER_SEE_NEXT" failed. Assert `Array.isArray(args)` at the top of the script. Recurred on 2026-10-19: the final round of the 42-issue sweep launched with `args.pending = '__FROM_FILE__'` and ran 0 agents. The relaunch added the `Array.isArray` guard. This line was the only copy of the guard. See [orchestration-memory-only-guards-recurred-in-the-next-sweep](orchestration-memory-only-guards-recurred-in-the-next-sweep.md).
- [MED] TaskStop does not kill subagent process trees. Afterwards kill leftovers with bracketed patterns, for example `pgrep -f '[l]efthook run pre-push'`. An unbracketed `pkill -f` matched its own monitor (exit 144). Recurred in the 2026-10-18 wave 2: two agents' `pgrep -f` waits matched their own monitor shells or another session's monitor. They switched to `kill -0 <pid>`, and one confirmed its push landed with `git ls-remote` instead.
- [MED] Per-agent private temp directories stopped a body-file collision. In the 42-issue sweep (2026-10-18), parallel agents wrote PR or comment bodies to one shared scratchpad, and one body collided. Each agent then got its own temp directory. The collision comes from the session facts only; no scratchpad file records which PR it hit.
- [MED] Separate CI green on two sibling PRs did not prove they work together. #6674 merged at 20:16 on 2026-10-18 (`a782716add`) with tests feeding `{"AllPassing": True}` and no `RequiredState`. #6695 made `_ci_state` stricter, so that fixture returned `_CI_UNKNOWN` (`detect_stale_bot_review.py:388-389`) and both tests reported NOT_READY. Only the full-suite pre-push run on #6695 caught it, before #6695 merged at 21:56 (`46977580f1`).
- [MED] Parallel agents exhaust the shared 5000 point/hr GraphQL budget (see [github-rate-limit-payload-does-not-predict-service](../ci/github-rate-limit-payload-does-not-predict-service.md)). Merge-stage polling should use REST `repos/{o}/{r}/commits/<sha>/check-runs`. Poll GraphQL-backed checks no more often than every 3 to 4 minutes per agent. One trip blocked the whole account for about 28 minutes.
- [MED] Route background commit-security findings where the pipeline blocks: an inline thread on the open PR, or an issue comment when the commit is unpushed. There were 4 true positives this sweep: merge_pr stacked TOCTOU (#6297), verify_dispatch_closure merge-base fail-open (#6415), api_examples SSRF (#5414), prepare_pr_body symlink (#6424).

## Related Memories

- [parallel-agent-execution-session-14](../parallel/parallel-agent-execution-session-14.md): Session 14 execution details
- [adr-042-python-first-enforcement](../adr/adr-042-python-first-enforcement.md): ADR conflict resolution pattern
- [codeql-security-integration](../codeql/codeql-security-integration.md): Tool reuse pattern
