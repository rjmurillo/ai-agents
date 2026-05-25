# Implementation: PR #1989 Recursive Failure Learnings

**Session**: 2026-05-10 (PR #1989 REQ-009 implementation)
**Confidence**: HIGH on all constraints below; observed within the same session that introduced each bug.

---

## Constraints (HIGH confidence)

**Use real PRs as the integration test bed, not synthetic fixtures.**
When testing a tool or script, run it against an open or recently-merged PR in the actual repo. PR #1989 was the test bed for M1 (stable-zero wrapper) and M4 (rework warning). M1 functioned correctly against PR #1989's real thread count. M4 returned 0 because threshold-6 was miscalibrated versus real edit counts (max = 4). Synthetic fixtures would have hidden both findings.
Source: User correction 2026-05-10: "you don't need a fixture repo, you have PRs and even this PR as a test bed."

**TDD must precede code, always. Tests drive from spec ACs, not from code.**
The failing test must come first, derived directly from the acceptance criteria in the /spec output. Code exists only to make the test pass. Writing tests that mirror already-written code is NOT TDD; it only confirms the code behaves consistently with itself, not correctly with the spec. PR #1989 had tests written after code for all milestones, which is why bots found semantic bugs the tests missed.
Source: User correction 2026-05-10: "TDD should be the first thing we activate. The tests should match the specification we created from /spec, and the code written to that specification."

**Guards and warning tools must self-apply during development.**
Any tool designed to detect a failure must be run against its own development branch before merge. M5 (bot-cascade pre-push warning) had bot-cascade bugs on the very PR that shipped it. If the guard doesn't fire when applied to the branch that introduces it, the threshold or detection logic is wrong.
Source: Observed in session 2026-05-10.

**Verify CLI flag and argparse semantics against live output before committing.**
`--diff-filter=R` looks like "show file names with rename detection" but restricts output to RENAMED files only. `action="store_true" default=True` looks like "default true, user can set" but makes the flag impossible to disable. Both looked correct visually and were semantically wrong. For any unfamiliar CLI flag or argparse pattern: run it, observe the output, confirm the behavior matches intent before committing.
Source: PR #1989 bugs found by cursor, copilot, coderabbit in session 2026-05-10.

---

## Constraints (MED confidence)

**Check memory entries for contradiction against code in the same diff.**
Session 15 sidecar said `get_unresolved_review_threads.py` "silently undercounts" and to always use the other script. M1 wrapper depended on that script in the same session. Before writing a memory entry, search for entries that might contradict the code being written. Before writing code, check existing memory entries for entries that might contradict the approach.
Source: Copilot thread PRRT_kwDOQoWRls6A7rwq on PR #1989 2026-05-10.

**Threshold-based detectors need calibration data from real PRs before committing.**
Threshold-6 for rework warning was arbitrary. Real maximum file edit count on the test-bed PR was 4. A threshold that never fires has zero signal value. Before committing any numeric threshold to a detector or warning tool, collect data from at least 5 real PRs and set the threshold at the P90.
Source: End-to-end test of M4 against PR #1989 2026-05-10.

**CI coverage gate module paths must be importable in CI.**
`--cov=wait_for_unresolved_zero` failed in CI because the module lives under `.claude/skills/**` and is not installed as a package. Before adding a `--cov=` gate to a workflow, verify the module can be imported by name in the CI Python environment, not just from the test script's sys.path manipulation.
Source: Copilot thread PRRT_kwDOQoWRls6A7rwP on PR #1989 2026-05-10.

**Keep failing PRs in draft, not abandoned. Bot findings are institutional knowledge.**
A draft PR with recorded bot threads documents failure modes. Closing it discards that evidence. Move to draft when further iteration is needed, not to abandoned/closed.
Source: User correction 2026-05-10: "Keep the PR so we can learn in the open. Move the PR to draft."

---

## Notes (LOW confidence)

Symptom-driven coding produces the same failure class regardless of what the code is supposed to fix. PR #1965 retro prescribed tooling mitigations for behavioral failures (read before write, check canonical source, co-change enumeration). PR #1989 built those tools with the same behavior. Tooling cannot substitute for actually reading the canonical source before touching code that relates to it.

---

## History

| Date | Bug | Root cause | How caught |
|------|-----|-----------|------------|
| 2026-05-10 | `--diff-filter=R` breaks rework signal | Semantic misread of git flag | 4 bots converged |
| 2026-05-10 | `--strict-pagination` unusable | argparse pattern copy-pasted | 2 bots |
| 2026-05-10 | Exit-code flattened to 1 | Didn't propagate contract | 2 bots |
| 2026-05-10 | Import-time crash in session-end | Informational coupled to critical path | 1 bot |
| 2026-05-10 | Subdir brace rename form wrong | Regex too narrow | 2 bots |
| 2026-05-10 | Unguarded subprocess.run | Missing except | 2 bots |
| 2026-05-10 | CI gate path not importable | Built gate without running it | 1 bot |
| 2026-05-10 | Recent-bot-review auth swallowed | Same fail-open pattern as ZX- | 1 bot |
| 2026-05-10 | Memory entry contradicts code | No contradiction check before writing | 1 bot |
| 2026-05-10 | Em-dashes in plan file | Project rule not self-applied | 1 bot |
