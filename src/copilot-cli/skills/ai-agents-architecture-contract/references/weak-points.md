# Known-Weak Points: Evidence and Consequence

The full evidence for the honestly-weak parts of the repository structure. SKILL.md Phase 7 keeps the compact list (name plus one-line consequence) so you know the hazard exists while working near it; this reference carries the dated evidence you cite when you act on one.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

State these plainly when working near them; do not design as if they were sound.

| Weak point | Evidence (as of 2026-07-03) | Consequence |
|---|---|---|
| Hook sources serve different consumers | `.claude/settings.json` has 3 events and 4 groups; `.claude/hooks/hooks.json` has 2 events and 2 groups | Do not force parity. Verify whether a hook is repository-only or vendored before editing either source |
| `src/claude/` manual dual-edit | `templates/README.md:131` | Shared-template edits silently skip the Claude surface unless you remember the second edit |
| Stale docs contradict reality | `CONTRIBUTING.md:155` said the removed PowerShell Generate-Agents command until PR #2871 repointed it to `python3 build/generate_agents.py`; zero `.ps1` files exist outside `.venv/` (ADR-042). `GENERATOR-FILES.md` lists `src/claude/` as a `generate_agents.py` output ("`src/claude/`, `src/copilot-cli/agents/`, `src/vs-code-agents/` (per platform YAML)"), but `generate_agents.py` contains no `src/claude` write and no claude platform YAML exists | Following docs verbatim fails; quote the canonical source when correcting (FM-9) |
| ruff is advisory in CI | `pytest.yml` comments around lines 107-119, issue #2194 style backlog | Lint debt accumulates invisibly; only syntax parsing blocks |
| Skill tests split by location | `pyproject.toml:41` `testpaths = ["tests"]`; `.claude/skills/<name>/tests/` NOT collected by default; `tests/skills/<name>/` is | Green CI does not prove skill tests ran; run them explicitly (`ai-agents-validation-and-qa`) |
| Proposed-ADR ambiguity | ADR-062/066/068/069/072 all read Proposed while their hooks, dispatcher, or doctrine are live | Status field is not a reliable "is this binding" signal; check enforcement, not status |
| EVENT telemetry consumer is thin | `push_guard_base.py` emits `EVENT=` lines; `guard-maturity` skill and `build/scripts/{aggregate_guard_intercepts,classify_guard_maturity}.py` consume, but no always-on pipeline is evident in-repo | Telemetry may be written and never read; verify before citing intercept ratios |
| Retro-cited SHAs unreachable from `main` | every PR squash-merges to a new SHA, so the PR-branch commits a retro recorded (`ddb76e0`, `01e76615a`) are never on `main`; whether they still resolve locally depends on which refs the clone carries | Archaeology still routes through retros and memories as primary sources, not git log |
