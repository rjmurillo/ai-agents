# Reviewer Guidance: What Not to Flag

<!-- vendor-portability: contributor-facing reference for the rjmurillo/ai-agents repo itself. It names upstream-only paths under .project-toolkit, scripts, templates, tests, src, lefthook.yml, pyproject.toml, .markdownlint-cli2.yaml, and .github because its audience is reviewers of this repo, not plugin consumers. Declared paths: .project-toolkit/memory/episodes, .project-toolkit/security/benchmarks/vulnerable_samples, scripts/ci/diff_line_scope.py, .markdownlint-cli2.yaml, src/claude/agents/qa.md, src/claude/skills/github/scripts/pr/get_pr_comments_by_reviewer.py, src/vs-code-agents, scripts/validation/skill_frontmatter.py, tests/validation/test_check_serena_memory_worktree_scope_failure_modes.py, docs/SKILL-AUTHORING.md -->

Read this before you review a pull request in this repo.
Each item below is a finding that reviewers kept raising and maintainers kept dismissing.
Skip these findings unless the diff breaks the reason given.
Before you cite a repo rule as authority, find it in a rule or config file.
The repo verified each reason against the code on 2026-11-26.

1. **Empty line sets from deletion-only hunks in diff-line ratchets.**
   A hunk header of `+N,0` touches no post-image line.
   A pure rename has no `+++ b/` hunk.
   `scripts/ci/diff_line_scope.py` gives a deletion-only hunk an empty set and leaves a pure rename out of the map, both on purpose.
   Counting them would flag unchanged neighbor lines (issue #2993).
2. **Content quality of generated session episodes.**
   The `extract-session-episodes` lefthook job writes episode JSON under `.project-toolkit/memory/episodes/` from session logs.
   Review the generator or the source log, not the generated text.
   A real defect in the generator is still in scope.
3. **Python style that ruff does not raise under the repo config.**
   Ruff with `[tool.ruff]` in `pyproject.toml` decides Python style.
   Its `target-version` is `py310`, a syntax floor that `pyproject.toml` explains, not the 3.14 runtime.
   Do not suggest syntax newer than `py310`.
   Raise style only when ruff raises it.
4. **Lint or format problems in the security benchmark corpus.**
   `.project-toolkit/security/benchmarks/vulnerable_samples/` holds deliberately vulnerable code.
   Its `# noqa: S...` comments are the answer key for external scanners.
   Do not reformat it, lint-fix it, or strip those comments.
   The tests and `conftest.py` beside it are ordinary code.
5. **Loosening a validation guard's regex to cut false positives.**
   Guards are strict on purpose.
   For an over-match, suggest a documented exemption or a match to the canonical regex.
   `.claude/rules/canonical-source-mirror.md` covers guards that mirror a canonical pattern.
6. **Workflow `pip install` pin changes without reading `pyproject.toml`.**
   A workflow pin such as `PyYAML==6.0.3` mirrors the same pin in `pyproject.toml`.
   Check the project pin first, and change both together or neither.
   `pip` itself has no project pin; its pin lives in `.github/workflows/pytest.yml` (see `rule-ci-scripts.md`).
7. **Markdown style that markdownlint passes.**
   `.markdownlint-cli2.yaml` decides Markdown style, and the pre-PR tooling check runs it.
   Do not flag blank lines around fences or lists (MD031, MD032) by hand.
   A fence nested in a fence needs a longer outer fence, such as four backticks around three.
   The rendered `src/claude/agents/qa.md` uses that form on purpose.
8. **`sys.exit(2)` for a config or environment error.**
   ADR-035 defines exit 2 as a usage, config, or environment error.
   Some older GitHub skill scripts still use 2 for "Not found", in the docstring and the code.
   One is `src/claude/skills/github/scripts/pr/get_pr_comments_by_reviewer.py`.
   ADR-035 maps not-found to 3, so those scripts are legacy, not a precedent.
   Judge a new exit code against ADR-035, not against them.
9. **Negative directives in agent and prompt files.**
   "Do not X" and "Never X" are normal prompt style here.
   No rule or validator requires affirmative phrasing.
   The prompt-engineer skill lists affirmative directives as one technique, not a rule.
10. **Missing boilerplate sections in agent prompts.**
    No rule requires a "Strategic Knowledge Available" section or a per-agent rollback section.
    Most agents have neither; git history is the rollback path.
    Do not ask to add them.
11. **MCP tool namespaces in VS Code agent files.**
    Files in `src/vs-code-agents/` list namespaces such as `context7/*` and `serena/*` on purpose.
    An agent degrades when that server is not configured.
12. **Skill frontmatter or sections the contract does not require.**
    `.claude/rules/claude-agents.md` MUST 2 requires `name`, `version`, and `description`.
    A missing `version` is a valid finding under that rule.
    `docs/SKILL-AUTHORING.md` lists `version` as optional, but the MUST rule wins.
    Do not flag a present `version`.
    `scripts/validation/skill_frontmatter.py` checks `allowed-tools` only when it is present.
    It caps `description` at 1024 characters, so a long router description is allowed.
    No rule requires a `surface` field or a `Decision Tree` or `Resources` section.
13. **CWE-78 on fixed-argument subprocess calls in tests.**
    A list-form call with constant arguments on a `tmp_path` path takes no request input.
    `_init_repo` in `tests/validation/test_check_serena_memory_worktree_scope_failure_modes.py` is one.
    Still flag `shell=True`, a string command, or any argument from the environment, CLI, network, or file content.
    Still flag the same call outside `tests/`.
