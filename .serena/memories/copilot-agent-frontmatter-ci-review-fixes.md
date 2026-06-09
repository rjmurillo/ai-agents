# Copilot agent frontmatter CI review fixes

PR #2501 follow-up addressed three review findings:

- `scripts/validation/validate_copilot_agent_frontmatter.py` now resolves `--agents-dir` under the repository root and rejects paths that escape after symlink resolution.
- The validator's raw frontmatter scanner treats only unindented `---` lines as fences, so indented fences inside block-scalar descriptions do not truncate YAML.
- `.github/workflows/validate-generated-agents.yml` installs `PyYAML==6.0.3` before running the validator so CI does not depend on runner-global packages.

Validation evidence: `uv run pytest tests/test_validate_copilot_agent_frontmatter.py tests/test_validation_pre_pr.py::TestParseYamlFrontmatter -q`, `python3 scripts/validation/validate_copilot_agent_frontmatter.py`, `python3 build/generate_agents.py --validate`, `python3 build/scripts/build_all.py --check`, workflow dry-run via `test_workflow_locally.py --workflow validate-generated-agents --dry-run`, and security review reported no vulnerabilities.

## Related

- [copilot-agent-frontmatter-ci-enforcement](copilot-agent-frontmatter-ci-enforcement.md)
- [copilot-hooks-observations](copilot-hooks-observations.md)
