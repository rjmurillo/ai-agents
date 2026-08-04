# Retrospective Section: PR #4017 and #4101 Review Thread Resolution

**Date**: 2026-08-01
**Scope**: Drain unresolved review threads on eval-cluster and parser-unification PRs
**Branches**: fix/eval-cluster, fix/eval-parser-unification

---

## Learnings Captured

### Re-measurement discipline confirmed again (111th time in this campaign)

Before acting on every reviewer comment, re-measured the premise against live code.

- Thread claiming ruff E402 would fire: measured with `uv run --frozen ruff check` - does not fire. Ruff recognizes the `sys.path.insert` pattern and suppresses E402 automatically. The existing `# noqa: E402` suppressions in other scripts predate this ruff behavior. Refuted with measurement; no code change.
- Two threads claiming a p-value inconsistency: verified the math. `6/8` sign criterion yields `p=0.289` under H0; the document said threshold was `0.05`. These cannot coexist. The reviewer was right. Fixed.
- Two threads on raw provider response truncation: confirmed `raw.strip()` was discarding whitespace in all five storage sites (four failure paths and success path). Reviewer was right. Fixed.

### Mutation harness for whitespace preservation requires per-path coverage

The first mutation run showed 3 surviving mutants because the whitespace-preservation test only used a `"  not json  "` payload (hitting the JSON-parse-failure path). The non-dict, two-verdicts, and shape-error paths all had separate storage sites that were not covered. Added per-path tests. Second run: 5/5 killed.

### Retrospective gate requires evidence in session log or a retro file

The push hook checks for retrospective patterns (heading `## Retrospective`, reference to `.agents/retrospective/`, or `learnings? captured`). A session log without those patterns is not enough. Creating a retro file under `.agents/retrospective/` (dated today) satisfies the gate.
