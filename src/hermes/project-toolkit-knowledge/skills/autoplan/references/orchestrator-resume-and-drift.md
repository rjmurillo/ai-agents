# Resume Check State Record and Anti-Drift Recovery

Loaded by the `orchestrator` agent when it resumes from a handoff and needs the state record fields, or when drift or context loss is detected. The agent body keeps the fail-closed Resume Check steps and a one-paragraph recovery rule.

## Resume Check state record

A resumable non-trivial task keeps one state record in the per-issue handoff: work-order fields, phase, exact next action, decisions with provenance (superseded marked), changed artifacts, validation run, blockers, residual risks, remote owner/name, branch, worktree, head SHA, timestamp. Label retrieved memory fact, decision, or hypothesis, and verified, unverified, or stale; HOLD on unverified load-bearing context. A completion summary is not completion evidence.

## Anti-Drift Recovery

### 7-Step Recovery

1. **ASSESS**: Is the approach fundamentally flawed? If so, stop and re-plan before touching code.
2. **CLEANUP**: Delete temp files, scratch scripts, and experimental code.
3. **REVERT**: Restore the last known working state (stash, checkout, or targeted revert) only for changes you own. Unclear ownership: HOLD and surface it.
4. **VERIFY**: `git status` clean, only intended changes remain.
5. **DOCUMENT**: Log the failed pattern to `memory/feedback-log.md` (or Serena memory).
6. **IMPLEMENT**: Try the researched alternative.
7. **RESUME**: Continue the original task with the corrected plan.

### Session Capture Protocol

Capture signal in the state record above. Session log creation is discontinued; use the per-issue handoff and Serena memory. Record blockers with workarounds attempted. Skip tool invocations, research that did not change the plan, routine reads, and superseded responses. A `workLog` entry is one or two sentences: the action or decision, then why. Keep it only if removing it would leave the next session unable to reproduce a decision or continue.
