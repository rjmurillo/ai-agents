# Ponytail Audit: whole-repo over-engineering scan

Skill: `ponytail-audit` from `DietrichGebert/ponytail`, already pinned for this
repo in `.github/copilot/settings.json` at
`2ed6c52c9d7e5e56942508591085fd45dea277d3`.

Scope per the skill: over-engineering and complexity only. Correctness bugs,
security holes, and performance are out of scope and were not hunted. Findings
only; nothing was applied.

Denominator: 9,765 tracked files, ~811k lines of tracked Python, ~130 MB
working tree.

## Findings, biggest cut first

1. `delete:` 26 skillforge slide-deck PNGs, 25.8 MB, carried in both plugin
   trees. Nothing. [`.claude/skills/skillforge/assets/images/`,
   `src/copilot-cli/skills/skillforge/assets/images/`]
2. `delete:` 121 colocated skill test files, 29,539 lines, that no runner
   collects. Move the few that assert something to `tests/skills/<name>/`.
   [`.claude/skills/*/tests/`, `src/copilot-cli/skills/*/tests/`]
3. `delete:` 9.2 MB claude-mem export blob with no code reader. Nothing.
   [`.claude-mem/memories/direct-backup-2026-01-03-1434-ai-agents.json`]
4. `yagni:` 33 `scripts/` modules, 11,405 lines, reachable only from their own
   tests. Delete the module and its test together. [`scripts/`, see Evidence 4]
5. `yagni:` session-log validator and its test, 6,952 lines, plus
   `measure_context_retrieval_metrics.py`, for an artifact type whose creation
   is discontinued. Keep a minimal validate-if-present path, drop the rest.
   [`scripts/validate_session_json.py`, `tests/test_validate_session_json.py`,
   `scripts/measure_context_retrieval_metrics.py`]
6. `yagni:` workflow engine with an ABC and three coordination strategies and
   zero production callers, 2,392 lines with its tests. Nothing.
   [`scripts/workflow/`]
7. `delete:` v0.3.0 orchestrator prototype: 1,339-line bash driver, its
   269-line test, a PowerShell-migration plan for a migration that finished,
   and four empty `.gitkeep` scaffolding directories. Nothing.
   [`.agents/projects/v0.3.0/`, `.agents/projects/v0.3.1/`]
8. `delete:` `.diffray/` rules engine, 2,080 lines across 12 files, with no
   reader and no invocation of the tool anywhere. Nothing. [`.diffray/`]
9. `delete:` root TypeScript island, 818 lines, with no root `package.json`, no
   `tsconfig` covering it, and no runner. Nothing. [`src/*.ts`,
   `src/transforms/`, `tests/*.test.ts`]
10. `delete:` two completed one-shot migration scripts, 631 lines, with zero
    references. Nothing. [`scripts/restructure_memories.py`,
    `scripts/mutation_test_proc_group.py`]
11. `stdlib:` 13 hand-rolled YAML frontmatter parsers in `scripts/` and
    `build/`. `frontmatter.loads` from the already-declared
    `python-frontmatter==1.3.0`, behind the existing
    `scripts/validation/yaml_utils.py`. [see Evidence 11]
12. `delete:` two inert `.disabled` droid workflows, 75 lines, that GitHub
    Actions never loads. Nothing. [`.github/workflows/droid.yml.disabled`,
    `.github/workflows/droid-review.yml.disabled`]
13. `delete:` empty coverage-threshold baseline, 54 lines, whose schema keys on
    `*.Tests.ps1` in a repo with zero PowerShell files. Nothing.
    [`.baseline/coverage-thresholds.json`, `.baseline/coverage-thresholds.schema.json`]
14. `delete:` `.skill` build artifact from a PowerShell generator that no longer
    exists, 24 lines across both trees, carrying a "GENERATED FILE / Do not edit"
    header that `.claude/rules/universal.md` MUST NOT item 5 forbids. Nothing.
    [`.claude/skills/steering-matcher/steering-matcher.skill`,
    `src/copilot-cli/skills/steering-matcher/steering-matcher.skill`]
15. `delete:` CodeQL suppressions file, 12 lines, all comments, not wired to the
    CodeQL workflow. Nothing. [`.github/codeql/suppressions.yml`]
16. `delete:` two pre-PR runner flags that are parsed and never read, one of
    them advertised in the PR template checklist. Nothing.
    [two `add_argument` blocks at `scripts/validation/pre_pr.py:263-272`]
17. `delete:` inert `warn` (8 keys) and `coupling.max` (2 keys) in the quality
    config, which the assessor never reads despite the file's own `_comment`
    claiming otherwise. Nothing. [`.qualityrc.json`]
18. `shrink:` `.agents/archive/session/` and `.agents/archive/sessions/`, a
    singular and plural pair holding 360 and 344 files, forcing
    `extract_session_episode.py:1614` to search both. One directory, one lookup.
    [`.agents/archive/`]
19. `shrink:` 1.0 MB JSON fixture loaded whole by one import test. A trimmed
    fixture with the same shape.
    [`2026-01-19-full-backup.json` at `tests/test_import_forgetful_memories.py:232`]

net: -56,500 lines, -35 MB, -0 deps possible.

Zero deps: every entry in `pyproject.toml` (`anthropic`, `jsonschema`,
`markdown-it-py`, `python-frontmatter`, `PyYAML`, `tiktoken`) and every dev
extra (`mypy`, `semgrep`, `bandit`, `pip-audit`, `ruff`, `pytest*`, `lefthook`,
`packaging`) has a verified importer or invocation site. Nothing to cut there.

## Evidence

1. 26 files, 25,832 KB. `.skillignore` line 11 lists `assets/images`, so the
   packager already excludes them from every install. Repo-wide search for each
   of the 13 basenames across `*.md`, `*.py`, `*.json`, `*.yml` returns zero
   hits, so no document embeds them either.
2. Every pytest invocation in the repository targets `tests/`:
   `scripts/ci/run_pytest_selected.py` partitions (`bulk`, `bulk-nested`,
   `mutation`, `safe-push`, `pr-autofix`), the four direct `pytest` lines in
   `.github/workflows/*.yml`, the plugin-manifest action, and the pre-push path
   (`git_hook_policy.py:7211`, `repo_root / "tests"`). `pyproject.toml:68` sets
   `testpaths = ["tests"]`. `scripts/validation/check_colocated_skill_tests.py`
   already calls these files a defect ("Colocated tests are copied into customer
   plugin installs and executed in consumer CI environments where they should
   never run") and blocks new ones, grandfathering the existing 121.
3. Search for `direct-backup-2026-01-03` outside `.agents/` and the file itself
   returns only a directory listing in `.claude-mem/memories/README.md`. The
   one analysis that mined it (`.agents/analysis/906-skill-learning-heuristic-enhancement.md`)
   finished in the past.
4. Each of the 33 has an importer only in its own test module. Roughly ten also
   carry a documented manual invocation in `scripts/README.md`,
   `scripts/eval/README.md`, or a `SKILL.md`, so triage before cutting:
   documented manual CLI is a weaker signal than a wired caller, but it is not
   nothing. Largest entries: `scripts/security/invoke_precommit_security.py`
   (1,019), `scripts/security/invoke_security_retrospective.py` (749),
   `scripts/eval/eval-reviewer-asymmetry.py` (675),
   `scripts/consolidate_skills.py` (641), `scripts/init_project.py` (613),
   `scripts/eval/eval_skill_router.py` (587). Two entries in this set,
   `scripts/compute_health_status.py` (540) and `scripts/error_classification.py`
   (341), are also part of finding 5 and are counted once.
   `scripts/validation/validate_seed_parity.py` is deliberately caller-free (its
   docstring reads "This is a FORENSIC TOOL, not a regression gate. Do NOT add
   it to CI") and is excluded from the count.
5. `.claude/rules/session-logs.md:9`: "Session log creation is discontinued: do
   not create a new `.agents/sessions/*.json` file." The 1,538 existing logs are
   frozen history. `scripts/validate_session_json.py` (1,694 lines) has no
   caller outside its own 5,258-line test;
   `git_hook_policy.py session` is a validate-if-present pre-commit gate that
   fires only when such a file is staged, which the rule tells contributors never
   to do. `scripts/measure_context_retrieval_metrics.py` parses the same frozen
   corpus and is imported only by `tests/test_context_retrieval_decision.py`.
6. `scripts/workflow/coordinator.py:29` defines `CoordinationStrategy(ABC)` with
   `CentralizedStrategy`, `HierarchicalStrategy`, and `MeshStrategy`. Searching
   for `WorkflowExecutor`, `get_strategy`, and each strategy name outside
   `scripts/workflow/` and `tests/` returns nothing. The `scripts.workflows`
   (plural) package is unrelated and live.
7. `.agents/projects/v0.3.0/scripts/orchestrate.sh` is 1,339 lines of bash in a
   repo where `AGENTS.md` forbids new bash scripts and ADR-042 mandates Python.
   Its siblings are four `.gitkeep`-only directories (`logs/`, `messages/inbox/`,
   `messages/outbox/`, `worktrees/`) and a `state/orchestrator.json`.
   `.agents/projects/v0.3.1/PowerShell-migration.md` plans a migration that is
   done: `git ls-files '*.ps1'` returns zero files.
8. The only in-repo mentions of `.diffray` are the root-clutter allowlist at
   `scripts/validation/git_hook_policy.py:97` and three markdownlint ignore
   globs. No workflow, hook, or script invokes a `diffray` binary.
   `.diffray/rules/powershell-patterns.yaml` (7 KB) targets a language with zero
   files here.
9. No `package.json` or `tsconfig.json` exists at the repository root; the only
   ones are under `packages/ai-agents-cli/`, which does not cover `src/*.ts`.
   The sole inbound references to these modules are the two sibling
   `tests/*.test.ts` files, which no runner executes.
10. `scripts/restructure_memories.py` docstring: "Restructure `.serena/memories/`
    into topic subdirectories", a completed one-time migration, mentioned only in
    two Serena memory prose lines. `scripts/mutation_test_proc_group.py`
    docstring: "Mutation harness for process-group timeout fix". Its only other
    mention is a synthetic PR-body fixture that quotes
    `encoding="utf-8"` at `tests/test_validation_pr_description.py:93`.
11. Sites: `build/scripts/generate_adr_index.py`,
    `build/scripts/generate_pr_quality_prompts.py`,
    `scripts/skill_description_budget.py`, `scripts/skill_registry.py`,
    `scripts/traceability/spec_utils.py`, `scripts/validate_skill_installation.py`,
    `scripts/validation/check_adr_lifecycle.py`,
    `scripts/validation/git_hook_policy.py`,
    `scripts/validation/skill_frontmatter.py`,
    `scripts/validation/spec_contradiction.py`,
    `scripts/validation/validate_copilot_agent_frontmatter.py`,
    `scripts/validation/validate_seed_parity.py`, and
    `scripts/validation/yaml_utils.py`. Only 5 files in the repository import
    `frontmatter` today. Three further copies live inside skill script
    directories (`adr-review`, `skillforge`, `spec-generator`) and are exempt:
    `.claude/rules/plugin-self-containment.md` requires shipped skills to resolve
    their own dependencies inside the plugin root.
16. `pre_pr.py` declares five arguments; the only `args.` reads in the file are
    `markdown_lint_only`, `markdown_files`, and `quick` (lines 306 to 311).
    `.github/PULL_REQUEST_TEMPLATE.md:157` tells every contributor to "pass
    `--quick` to skip slow validations or `--skip-tests` for very fast
    iterations". The flag's help text says "Skip Pester unit tests" and the
    module docstring line 9 still lists "Pester Tests (all unit tests)", in a
    repo with zero PowerShell files.
17. `assess.py` reads `thresholds["coupling"].get("min")` at line 1522 and has
    no `get("max")` or `["max"]` anywhere. `.qualityrc.json` gives `coupling`
    only `max`, in both `thresholds` and `context.test`, so the coupling gate
    never fires. The skill's own test says of `warn`: "no `min`; `warn` is an
    ignored unknown key".

## Deliberately not flagged

The three-tree mirror (`.claude/`, `src/copilot-cli/`, `.github/`) looks like
21 MB of duplication and is not. `.claude/skills` and `src/copilot-cli/skills`
are byte-identical for 88 of 94 `SKILL.md` files, and `scripts/github_core`,
`scripts/ai_review_common`, and `scripts/hook_utilities` each exist three times,
but `scripts/sync_plugin_lib.py` generates the copies from a single source and
`.claude/rules/plugin-self-containment.md` requires each plugin root to ship
self-contained. The apparent drift between `.github/instructions/` and
`src/copilot-cli/instructions/` (11 of 24 files differ) is also by design:
the `keep_internal` switch documented at `build/scripts/generate_rules.py:306-312`
strips upstream-only path globs from the distributed copy, because a consumer
does not have the internal directories. Cutting to one tree would be a packaging
rewrite, which is ocean, not lake.

Also not flagged: `scripts/memory/memory_health.py` is documented as a runnable
command in `.serena/memories/README.md:112` and
`.agents/governance/MEMORY-MANAGEMENT.md:588`, so it is a manual CLI rather than
dead code. Worth a separate look: the documented form
`python3 -m scripts.memory.memory_health` cannot work, because `scripts/memory/`
has no `__init__.py`.
