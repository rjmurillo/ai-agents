## Constraints

- New skill tests go under `tests/skills/<name>/`. `check_colocated_skill_tests.py` blocks a newly added file colocated under `.claude/skills/`, `src/copilot-cli/skills/` or `src/claude/skills/` (all three populated); pre-existing ones grandfathered, and a mirror copy of a grandfathered `.claude/skills/` test is allowed.
- `tests/fixtures/guard_corpus_baseline.json` is a pinned finding set; `tests/test_guard_diff.py` fails on a lost finding, repair edits the baseline with a justification.
- No write rooted at `PROJECT_ROOT`/`REPO_ROOT`/`ROOT` outside `tmp_path`/`.pytest_tmp/`: `check_test_tree_writes.py`.
- No `test_*` nested inside another function: `check_nested_tests.py`; blind spot below.
- A `SKILL.md` naming a script invocation plus an exit code needs a test under `tests/`: `check_skill_contract_tests.py`.
- `tests/evals/rule-scenarios/<rule>.json` and `skill-scenarios/<skill>.json` back `check_rule_activation_coverage.py`: unparseable JSON, or a scenario naming a deleted rule or skill, exits 2; an uncovered new rule or skill exits 1 against `rule_activation_coverage_baseline.json`.
