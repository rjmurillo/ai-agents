# Skill Sidecar Learnings: Eval Harness

**Last Updated**: 2026-05-30
**Sessions Analyzed**: 1 (wiki-rubric audit #2126/#2136)
**Related**: agent-prompt-optimization-observations.md (fixture-design-for-effectiveness lesson lives there)

## Constraints (HIGH confidence)

- Run one agent's eval: `python3 scripts/eval/eval-agent-vs-baseline.py --agent <name> --fixtures evals/<name>-spike/fixtures --n-runs 3 --model claude-sonnet-4-6` from repo root. `ANTHROPIC_API_KEY` is read from env or `.env`. The agent-under-test "variant" is `templates/agents/<name>.shared.md` (read as the system prompt); baseline prompt is fixed "Review the following input." `--dry-run` validates fixtures + prints the plan with ZERO spend (the only no-API path; no `--mock` exists).
- Custom eval scripts MUST use the repo's own transport `from _anthropic_api import call_api` (urllib-based, `scripts/eval/_anthropic_api.py`). `import anthropic` FAILS — the SDK is not installed. The main harness works because it uses `call_api`, not the SDK. (Bug hit: `eval_skill_router.py` rc=3 "SDK not installed".)

## Preferences (MED confidence)

- Fixture format: JSON, one per file in `evals/<name>-spike/fixtures/*.json`. Fields: `schemaVersion` (must be 1), `id` (unique across corpus), `input`, `provenance` (`synthetic|public-cve|paraphrased-from-public`), `assertions` (each `{"kind":"verdict","expected_value":"IDENTIFY|OK|ESCALATE"}` OR `{"kind":"regex","pattern":"..."}`; never both on one assertion), `tags`. Validated by `FixtureValidator` (`_eval_agent_types.py`). No manifest/registry; the runner globs `fixtures/*.json`.
- Reports: `evals/<name>-spike/reports/<RUN_ID>/report.json` (+ `REPORT.md`); per-call records in `runs/<RUN_ID>/runs.jsonl` (the agent's actual output is the `raw_response` field). `report.json` carries `agent_recall`, `baseline_recall`, `recall_delta`, `bootstrap_ci_95`, `per_fixture_pass_rates`, and `*_sha` provenance. To detect regression after a prompt edit: re-run the SAME fixtures, compare new `recall_delta`/CI to the committed baseline report (comparable only when `fixture_set_sha` matches). The harness has NO built-in diff command.
- Cost ~$0.40-1.40 per agent at `--n-runs 3` (calls = n_runs x fixtures x 2 variants). Flakiness halt: if >30% of fixtures are intra-run-variant flaky, the runner emits informational metrics and exits non-zero (ADR-058) — a delta with flaky=true is directional, not significant.

## Edge Cases (MED confidence)

- DEFERRED agents (no `templates/agents/<name>.shared.md`): the harness cannot load the variant, so it cannot eval them. context-retrieval, quality-auditor, spec-generator are DEFERRED. To eval them you must first author the `.shared.md` template + a spike.
- Two skill eval systems exist: knowledge-integration (`scripts/eval/eval-knowledge-integration.py`, prompts in `tests/evals/skills/*.json`) and agent-vs-baseline. A true skill ROUTER/trigger eval (does query X load skill Y?) does NOT exist; author one if needed (`eval_skill_router.py` was a first attempt — compares before/after skill descriptions on disambiguation queries).
- `validate-skill.py` (SkillForge) has a CWE-22 cwd path guard — it rejects targets outside cwd; `cd` into a worktree to validate its copy. See `mem:ci-infrastructure-observations` for the build/parity/drift model.

## Notes for Review (LOW confidence)

- The verdict-vocabulary confound (harness forces IDENTIFY|OK|ESCALATE) is the single biggest measurement-noise source; fixture-design workaround (score behavioural regex, not verdict token) is documented in agent-prompt-optimization-observations.md.
