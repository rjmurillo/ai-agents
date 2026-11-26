# Reviewer Guidance: What Not to Flag

<!-- vendor-portability: contributor-facing reference for the rjmurillo/ai-agents repo itself. It names upstream-only paths under .project-toolkit, scripts, lefthook.yml, pyproject.toml, and .github because its audience is reviewers of this repo, not plugin consumers. Declared paths: .project-toolkit/memory/episodes, .project-toolkit/security/benchmarks/vulnerable_samples, scripts/ci/diff_line_scope.py -->

Read this before you review a pull request in this repo.
Each item below is a finding that reviewers kept raising and maintainers kept dismissing.
Skip these findings unless the diff breaks the reason given.
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
   Its target is `py310`, so do not suggest syntax newer than that.
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
