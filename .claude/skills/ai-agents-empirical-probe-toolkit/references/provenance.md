# Empirical Probe Toolkit: Provenance and Maintenance

Sources and re-verification one-liners for every load-bearing fact in `../SKILL.md`. Consult when auditing or refreshing the toolkit.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

Verified 2026-07-03 against the working tree.

| Fact | Source | Re-verify |
|------|--------|-----------|
| #2205 probe story, first-fix defects | `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:49-50` | `grep -n "session 1873" .agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` |
| Plugin-root env contract, Copilot CLI 1.0.57 | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` | `cat .serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` |
| Payload casing contract, CLI 1.0.58 | `.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:33,47,71` | `grep -n "toolArgs" .agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md` |
| M4 threshold 6 vs max 4; last-5-PRs rule | `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:70-73,153` | `grep -n "Threshold = 6" .agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` |
| #1887 Phase-6 audit 0/35 | `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md:199,230` | `grep -n "Total preventable" .agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` |
| Eval commands and flags | `scripts/eval/eval-prompt-change.py:1-60`, `scripts/eval/eval-agent-vs-baseline.py:447-475` | `python3 scripts/eval/eval-prompt-change.py --help` |
| Scenario/fixture locations | `tests/evals/`, `evals/` | `ls tests/evals/ evals/` |
| Verbatim-quote rule (7 fix commits) | `.claude/rules/canonical-source-mirror.md` | `sed -n '1,30p' .claude/rules/canonical-source-mirror.md` |
| CONTRIBUTING pwsh commands are dead | `CONTRIBUTING.md:155`; no `.ps1` outside `.venv` | `find . -name '*.ps1' -not -path './.venv/*'` |
| Reproduce-on-main rule (PR #1361) | `.serena/memories/ci-infrastructure-observations.md:8` | `sed -n '8p' .serena/memories/ci-infrastructure-observations.md` |
| Runtime-contract exemplar passes (6 tests) | `tests/build_scripts/test_generate_hooks_runtime_contract.py` | `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q` |
| FM-9, FM-11 catalog rows | `.agents/governance/FAILURE-MODES.md:14-27` | `sed -n '14,28p' .agents/governance/FAILURE-MODES.md` |

Volatile facts to re-check when touching this skill: Copilot CLI version pins (1.0.57/1.0.58 were the measured versions, not the current ones), the `tests/evals/` scenario inventory, and whether ADR-057's flakiness protocol has been amended.
