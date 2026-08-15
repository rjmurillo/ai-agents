---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14712-issue-5074-merge-resolver-rename-rule.json
qaCommit: c0d7bf451fd37e4fc2bdc01f5c0212743ed7e7b1
---

# Issue 5074 Merge Resolver Rename Rule QA

## Scope

Session-log add/add conflicts recur (two sessions allocating the same number),
and the correct resolution lived only in a retrospective, not in the guidance
the merge-resolver agent loads during conflict resolution. Worse, the agent's
Phase 2 classification listed session artifacts (`.agents/*`) as auto-resolvable
by accepting the base branch version, which on an add/add discards the head
branch's own record. This change encodes the rename-never-content-merge rule in
every merge-resolver guidance surface and fixes the wrong classification.

Files under test:

- `templates/agents/merge-resolver.shared.md` (canonical template)
- `src/claude/merge-resolver.md` (hand-maintained)
- `.claude/agents/merge-resolver.md` (hand-maintained)
- `.github/agents/merge-resolver.agent.md` (hand-maintained)
- `src/copilot-cli/agents/merge-resolver.agent.md` (generated)
- `src/vs-code-agents/merge-resolver.agent.md` (generated)
- `.claude/skills/merge-resolver/SKILL.md` (version 2.3.0)
- `.claude/skills/merge-resolver/references/strategies.md`
- `build/scripts/detect_agent_drift.py` (baseline re-measure only)
- `scripts/validation/git_hook_policy.py` (observation-sync internal budget)
- `tests/test_lefthook_integration.py`, `tests/test_claude_mem_scripts.py`,
  `.claude/skills/orphan-ref-validator/tests/test_scan.py` and its
  `src/copilot-cli` mirror (budget tests plus root-environment skip guards)

## Acceptance Criteria

Quoted from issue #5074:

- [x] merge-resolver guidance names the artifact classes and the rename
  resolution. Every guidance surface now carries a "Rename, never
  content-merge" class listing session logs (`.agents/sessions/*`), QA reports
  (`.agents/qa/*`), and retrospectives (`.agents/retrospective/*`), with the
  keep-both, suffix-rename, update-references procedure.
- [x] The anti-pattern (content-merging two session logs) is stated with the
  4856 citation. Each copy's anti-pattern table gains "Content-merge an add/add
  session-log conflict", and the class prose quotes the retro's finding that
  merging both sessions' prose into one file would have destroyed two accurate
  records to produce one false one, citing
  `.agents/retrospective/2026-08-10-pr-4856-session-log-collision.md` and
  issue #4751 for allocation-time prevention.

## Verification Evidence

| Check | Command | Result |
|-------|---------|--------|
| Wording identical across all six agent copies | `grep -c "An add/add conflict here means two branches wrote different records" templates/agents/merge-resolver.shared.md src/claude/merge-resolver.md .claude/agents/merge-resolver.md .github/agents/merge-resolver.agent.md src/copilot-cli/agents/merge-resolver.agent.md src/vs-code-agents/merge-resolver.agent.md` | 1 per file |
| Generator run after template edit | `uv run python build/generate_agents.py` | Generated 93 files; only merge-resolver outputs changed |
| Drift detection green after floor re-measure | `python3 build/scripts/detect_agent_drift.py` | `OK (baselined) (20.7% similar)` for both merge-resolver comparisons; `RESULT: No significant drift detected` |
| Drift detector unit tests | `uv run pytest tests/test_detect_agent_drift.py -x -q` | 52 passed |
| Ruff on edited script | `uv run ruff check` and `ruff format --check` on `build/scripts/detect_agent_drift.py` | clean |
| Markdown lint | `npx markdownlint-cli2` on all changed markdown files | 0 issues (`.agents/**` and `.github/agents/**` excluded by config) |
| Session log validates | `uv run python scripts/validate_session_json.py .agents/sessions/2026-08-15-session-14712-issue-5074-merge-resolver-rename-rule.json` | PASS after QA report landed |
| Observation-sync budget behavior | `uv run pytest tests/test_lefthook_integration.py -k sync_observations -q` | 4 passed (existing pair plus mid-list stop and exhausted-budget edge) |
| Root-skip guards leave non-root coverage intact | `uv run pytest tests/test_claude_mem_scripts.py .claude/skills/orphan-ref-validator/tests/test_scan.py -q` | 12 passed 1 skipped; 227 passed 1 skipped (skips are the root-environment guards firing in this root container; CI runners are non-root and execute them) |

## Known Gaps

- `resolve_pr_conflicts.py` `AUTO_RESOLVABLE_PATTERNS` still matches
  `.agents/sessions/*` and resolves by accept-theirs, which performs only half
  of the documented resolution on an add/add: it keeps main's record and
  silently discards the branch's. The SKILL.md caveat documents the manual
  rename half. Teaching the script the rename is follow-up work, out of scope
  for this docs issue.
- The drift floor drop (20.9 to 20.7) is a measurement artifact of adding
  identical prose to two intentionally divergent shapes, not new divergence;
  the comment above `KNOWN_BASELINE_DRIFT` records the re-measure rationale.
