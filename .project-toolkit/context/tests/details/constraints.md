## Constraints

- New skill tests go under `tests/skills/<name>/` (`check_colocated_skill_tests.py` blocks colocated tests under `.claude/skills/`, `src/copilot-cli/skills/`, `src/claude/skills/`).
- `tests/fixtures/guard_corpus_baseline.json`: pinned finding set; `tests/test_guard_diff.py` fails on lost findings.
- No write under `PROJECT_ROOT`/`REPO_ROOT`/`ROOT` outside `tmp_path`/`.pytest_tmp/`: `check_test_tree_writes.py`.
- No nested `test_*` inside functions: `check_nested_tests.py` (blind spot below).
- A `SKILL.md` naming a script + exit code needs a test under `tests/`: `check_skill_contract_tests.py`.
- `tests/evals/rule-scenarios/<rule>.json` and `skill-scenarios/<skill>.json` back `check_rule_activation_coverage.py` (exit 2 on bad JSON/deleted item; exit 1 on uncovered new rule/skill vs `rule_activation_coverage_baseline.json`).
