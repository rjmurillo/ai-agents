---
name: ai-agents-generation-and-release
description: Operate the ai-agents generation and release machinery, covering the seven build_all.py generators, generate_agents.py, the drift gates, the version-free plugin manifests, and the npm publish path. Use when you say `regenerate the mirrors`, `run the drift checks`, `why is the plugin version gate red`, `release the npm cli`. Do NOT use for environment setup (use `ai-agents-build-and-env`) or architecture rationale (use `ai-agents-architecture-contract`).
version: 1.0.0
license: MIT
metadata:
  distribution: repo-local
  routing:
    role: conditional-adjunct
    invoker: ai-agents-build-and-env
    trigger: build-and-env redirects release work here
    user-facing: false
---

# ai-agents Generation and Release

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers. Declared paths: .claude/lib, .project-toolkit/architecture/ADR-036-two-source-agent-template-architecture.md, .project-toolkit/architecture/ADR-052-template-strategy.md, build/generate_agents.py, build/scripts/build_all.py, build/scripts/check_plugin_manifest_parity.py, build/scripts/detect_agent_drift.py, build/scripts/lib_mirror.py, build/scripts/validate_plugin_version_bump.py, build/scripts/yaml_loader.py, scripts/ai_review_common, scripts/github_core, scripts/hook_utilities, templates/agents, templates/platforms/binplace.yaml -->
Runbook for the build, generation, mirroring, versioning, and release machinery. Facts that change (generator list, owned prefixes, skill counts, gate wiring) come from the script in Phase 1, not from this prose.

Reached from `ai-agents-build-and-env`, which names this skill back. No root router exists; enter by trigger phrase.

Jargon, defined once:

- Generator: a Python function or script that reads a canonical tree and writes a derived (generated) tree.
- Drift: the generated tree no longer matches what the generators would produce from the canonical tree.
- Canonical: the tree you are allowed to edit. Generated trees are outputs; you never hand-edit them.
- Semver: semantic version string MAJOR.MINOR.PATCH. The plugin manifests carry no version at all (ADR-092); the npm package still does.

## Triggers

- `regenerate the mirrors`
- `run the drift checks`
- `why is the plugin version gate red`
- `release the npm cli`
- `why is the drift gate red`

## When NOT to Use This Skill

| You want | Use instead |
|----------|-------------|
| Set up the dev environment, uv, hooks | `ai-agents-build-and-env` |
| WHY the seam is shaped this way, invariants | `ai-agents-architecture-contract` |
| Triage a red CI gate you do not understand | `ai-agents-debugging-playbook` |
| Change classification, commit caps, review gates | `ai-agents-change-control` |
| Escape hatches like the drift allowlist | `ai-agents-config-catalog` |

## Process

### Phase 1: Know the Seam Before You Edit

The generation seam is ASYMMETRIC (ADR-072, accepted and not yet implemented, refines it; the running system is what follows). Find your file BEFORE editing. Editing a generated tree is the classic failure (see Anti-Patterns).

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/generator_inventory.py" --repo . path <repo-path>
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/generator_inventory.py" --repo . generators
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/generator_inventory.py" --repo . skills
```

- `path` answers which tree is canonical for a repo path and what regenerates it, from `templates/platforms/binplace.yaml` rows plus `OWNED_PREFIXES`. Exit 1 means no row covers the path. It does not see hand-maintained exceptions inside a generated tree, such as a shipped skill's `scripts/` and `references/`.
- `generators` prints the `GENERATORS` order from `build/scripts/build_all.py`, the `OWNED_PREFIXES` tuple, and the exit-2 producer count its docstring states. Order is load-bearing.
- `skills` counts `templates/skills/*.SKILL.md.tmpl` and lists the `distribution: repo-local` skills. It does not say which are shipped to a given plugin root.

Rules that hold across the rows (the tables are in [references/seam-tables.md](references/seam-tables.md)):

- Edit `templates/` and the `scripts/{hook_utilities,github_core,ai_review_common}` packages. Everything under `src/copilot-cli/`, `src/vs-code-agents/`, `.github/instructions/`, and `src/claude/{agents,rules,hooks,settings.json}` is generated.
- Edit a skill's `SKILL.md` only through `templates/skills/<name>.SKILL.md.tmpl` (ADR-108, ADR-109 B3). `.claude/skills/<name>` links to `src/claude/skills/<name>` for shipped skills (ADR-119). A repo-local skill renders straight to `.claude/skills/<name>/`.
- `build_all.py` exits 2 with `REQ-003-010 VIOLATION` if a generator writes under `.claude/`, except through a `binplace.yaml` `install_tree`. Regenerating reproduces that exit; it is a policy violation, not staleness.

### Phase 2: Regenerate After Editing a Canonical Surface

Commit the canonical edit and the regenerated output TOGETHER, or the drift gates go red.

Interpreter: `build/generate_agents.py` and `build_all.py` import PyYAML through `build/scripts/yaml_loader.py`. Run them as `uv run python <script>` locally. CI can use bare `python3` because `.github/actions/setup-code-env` installs the locked dependencies first.

| You edited | Run | Then |
|------------|-----|------|
| `templates/agents/*.shared.md` | `uv run python build/generate_agents.py`, then `uv run python build/scripts/build_all.py` | commit the template and every regenerated file, including `src/claude/agents/`. |
| `templates/skills/<name>.SKILL.md.tmpl` or `.claude/rules/` | `uv run python build/scripts/build_all.py` | commit the template and both rendered copies. No manifest edit (Phase 4). |
| `.claude/hooks/` or `.claude/settings.json` | `uv run python build/scripts/build_all.py` | same. Regenerate BEFORE pushing: no pre-push job runs `--check`, so the first red is CI. |
| `scripts/hook_utilities/`, `scripts/github_core/`, `scripts/ai_review_common/` | `uv run python build/scripts/build_all.py` | one command writes both lib trees and binplaces `.claude/lib/`. |
| `src/claude/AGENTS.md`, `src/claude/claude-instructions.template.md` | nothing to regenerate | commit directly. |

Flags, read from source:

- `build/generate_agents.py`: `--validate` (CI compare mode), `--what-if` (dry run), `--templates-path`, `--output-root`. Exit 0 ok, 1 logic error or drift, 2 config error.
- `build/scripts/build_all.py`: `--check` (staleness gate; snapshots and restores owned trees), `--clean`, `--audit-format json`, `--platform copilot-cli`. Exit codes 0, 1, 2, 3 are defined in the `EXIT CODES` block of its module docstring; read that block for the producer list. Only the staleness producer of exit 2 is cleared by regenerating. Every git-read failure is exit 3, which keeps "git is missing" apart from "your tree is stale".
- `build/scripts/lib_mirror.py`: the lib copy, run by `build_all.py`. Do not "fix" `.claude/lib/` imports by hand.

### Phase 3: Run the Drift Gates Locally Before Pushing

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/generator_inventory.py" --repo . gates
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/instruments.py" --repo . run build-all-check
```

`gates` maps each drift gate to the lefthook job or workflow job that runs it and exits 1 for a gate with no wiring. The gate list, local commands, and caveats are in [references/drift-gates.md](references/drift-gates.md). Its answer does not say a gate is green, only where it runs.

When a gate is red, the output shows the DIFFERENCE, not the DIRECTION. Ask which side is canonical before touching anything. Fix is always: edit canonical, rerun the generator, commit both. The 2025-12-15 incident (edited source to match generated) is in `drift-gates.md`. An emergency bypass marker exists; see `ai-agents-config-catalog` and route the decision through `ai-agents-change-control`.

The installed-plugin Copilot hook E2E must run in an isolated `HOME` and `COPILOT_HOME`, never the live Copilot home. The commands and the incident are in `drift-gates.md`.

### Phase 4: Plugin Manifests Carry No Version

Two Claude-plugin manifests exist; `.claude/.claude-plugin/plugin.json` is retired. Other plugin.json files under `src/` belong to other hosts and are out of scope here.

| Tree | Manifest |
|------|----------|
| `src/claude/` | `src/claude/.claude-plugin/plugin.json` |
| `src/copilot-cli/` | `src/copilot-cli/.claude-plugin/plugin.json` |

`.claude/` is not a marketplace-listed root. Its template-owned files are binplaced from `src/claude/`; skill `scripts/`, `references/`, and `tests/` stay hand-maintained.

The rule (docstring of `build/scripts/validate_plugin_version_bump.py`): neither manifest, and no entry in any `marketplace.json`, may carry a `version` field. Claude Code then resolves freshness from the git commit SHA, which moves on every merge. ADR-092 reverses ADR-079's hand-bumped rule (ADR-079 was superseded by ADR-091, and ADR-091 by ADR-092) after ADR-092 measured 14 of 22 conflicting PRs conflicting on that one line.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/instruments.py" --repo . run version-field
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/instruments.py" --repo . run manifest-parity
```

`version-field` fails when a manifest or marketplace entry carries `version`. `manifest-parity` checks description component counts only. Neither lists which manifests exist; the table above does.

Consequences:

- Any `.claude/` content edit regenerates `src/copilot-cli/` too, but neither manifest changes.
- `.github/instructions/` and `src/vs-code-agents/` carry no plugin.json.

### Phase 5: npm Release Path

The npm surface is `packages/ai-agents-cli` (package
`@rjmurillo/ai-agents`; read `package.json` for the current version). It vendors
the Claude kit into consumer repos.

`RELEASING.md` (repo root) owns the release procedure: setup, publish, dry run,
verification, rollback, and troubleshooting. Follow it step by step and do not
copy its steps here, because they change with the publish gate.

Durable distinctions to keep in mind:

- The only live CI publish route is a manual `workflow_dispatch` run of `.github/workflows/publish.yml` on the default branch. That dispatch run applies the ADR-113 promotion gate, enforcing for a real publish and advisory for a dry run (`dry-run` defaults to `true`). The one-time First publish in RELEASING.md runs locally, outside CI, and runs no promotion gate.
- The `v*` tag trigger is dormant. A tag push runs, then the first job refuses it, so pushing a tag does not publish. A `v*` tag ruleset is the owner action that would revive it (ADR-113 Resolved Question 2).
- The candidate is the head of the default branch, so the version bump in `packages/ai-agents-cli/package.json` must merge first, through the normal PR flow (branch discipline and review per `ai-agents-change-control`).
- Rollback is roll-forward: npm unpublish is restricted, so fix, bump the patch version, merge, and dispatch again (RELEASING.md Rollback procedures).
- Local sanity: `bun run build`, `bun test`, and `bun run typecheck` in `packages/ai-agents-cli`; all three should pass.

## Scripts

Both scripts are read-only, print JSON with an `examined` count, and answer `--help`. Exit 0 ok, 1 findings, 2 bad arguments or configuration. Exit 3 means `instruments.py` could not start a run target; `generator_inventory.py` reserves it and never returns it.

- `generator_inventory.py` with `generators`, `path <repo-path>`, `skills`, `gates` (Phases 1 and 3).
- `instruments.py` with `list` and `run <id>`; it links the build and manifest checks and passes the child's exit code through.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/instruments.py" --repo . list
```

## Anti-Patterns

| Anti-pattern | Why it burns you | Do instead |
|--------------|------------------|------------|
| Hand-editing `src/copilot-cli/`, `src/vs-code-agents/`, `.github/instructions/`, `.claude/lib/` | Next regen silently overwrites your edit; ruff exempts generated Python under `src/copilot-cli/{hooks,skills}/**/*.py` (`pyproject.toml [tool.ruff.lint.per-file-ignores]`), so lint will not look at it | Edit the canonical tree (`path` command), regenerate |
| Editing source to make a drift gate green | The 2025-12-15 disaster; drift output shows difference, not direction | Identify the canonical side first, regenerate outward |
| Editing `.claude/lib/` or `src/copilot-cli/lib/` by hand | Both are generated; the next `build_all.py` run reverts you | Edit `scripts/{hook_utilities,github_core,ai_review_common}`, run `build_all.py` |
| Bumping the two manifests in lockstep to satisfy version parity | Parity retired with the field (ADR-092); the bump itself now fails the gate | Nothing to bump; leave both manifests version-free |
| Re-adding a `version` to a manifest to clear a red gate | The gate fails on the field's presence, so the red is permanent | Delete the field; freshness already tracks the commit SHA |
| Treating `Dropped: N` as normal without checking the source | An unexplained drop means contract drift | Read the generation audit log, identify the source registration, require an explicit `eventDrop` decision |
| Running `build_all.py` with bare `python3` in a fresh shell | PyYAML lives in the venv; import fails | `uv run python build/scripts/build_all.py` |
| Running installed-plugin E2E against live `~/.copilot` | Version skew and ambiguous uninstall mutate active hooks; a missing hook root can deny every matching tool | Isolate `HOME` and `COPILOT_HOME` (see `drift-gates.md`) |
| Treating `src/claude/` as wholly hand-maintained | Its `agents/`, `rules/`, `hooks/`, `settings.json`, and `skills/*/SKILL.md` are generated (ADR-109); the ADR-036 exception is superseded | Run the `path` command; hand-edit only `AGENTS.md`, `claude-instructions.template.md`, and non-SKILL skill files |

## Verification

Before pushing a change that touched a canonical or generated surface:

- [ ] `uv run python build/generate_agents.py --validate` exits 0
- [ ] `uv run python build/scripts/build_all.py --check` exits 0 (on 2, read stderr first: regenerate only for staleness, not for an unreadable, redirecting, or nested-repo owned path, and not for a REQ-003-010 write)
- [ ] `python3 build/scripts/check_plugin_manifest_parity.py` exits 0
- [ ] `python3 build/scripts/validate_plugin_version_bump.py` exits 0
- [ ] Canonical edit and regenerated output are staged in the same commit set
- [ ] For an npm release: any `release-tag` input matches the `packages/ai-agents-cli/package.json` version exactly

## Provenance and Maintenance

Volatile facts come from the script in Phase 1, not from this file. `reverify.json` holds the checks that pin the paths and source strings this skill cites. Run the drift command after any edit here:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skill-bootstrap/scripts/bootstrap_drift.py" check --repo . --skills-root .claude/skills --name ai-agents-generation-and-release --require
```

`python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-generation-and-release/scripts/instruments.py" --repo . list` prints every linked instrument and exits 1 when one is missing.

| Fact | Source | Re-verify |
|------|--------|-----------|
| .claude/ no-write invariant | `CLAUDE_GUARD_PREFIX`, the `claude_baseline` snapshot in `run`, `assert_no_claude_writes` in `build/scripts/build_all.py` | `grep -n "REQ-003-010" build/scripts/build_all.py` |
| generate_agents flags and exit codes | `build/generate_agents.py` docstring | `uv run python build/generate_agents.py --help` |
| lib mirror pairs | `PACKAGES` in `build/scripts/lib_mirror.py` | `grep -n PACKAGES build/scripts/lib_mirror.py` |
| Version-field prohibition and ADR-092 reversal | `build/scripts/validate_plugin_version_bump.py` docstring | `grep -n "WHY THE FIELD MUST BE ABSENT" build/scripts/validate_plugin_version_bump.py` |
| Weekly semantic drift cron, threshold 80 | `.github/workflows/drift-detection.yml`; argparse default in `detect_agent_drift.py` | `grep -n "cron" .github/workflows/drift-detection.yml && grep -n "default=80" build/scripts/detect_agent_drift.py` |
| Git hook jobs and filters | `lefthook.yml` | `uv run --frozen lefthook validate` |
| npm package, bun build, dispatch-only publish route (re-verified 2026-10-14) | packages/ai-agents-cli/package.json; RELEASING.md; the header comment of .github/workflows/publish.yml | `grep -n '"build":' packages/ai-agents-cli/package.json && grep -n "dormant" RELEASING.md .github/workflows/publish.yml` |
| Audit log path, gitignored | `.gitignore` | `grep -n "build/audit" .gitignore` |
| ADR-036 and ADR-052 superseded, ADR-108 and ADR-109 accepted | the four ADR records | `grep -l "^status: superseded$" .project-toolkit/architecture/ADR-036-two-source-agent-template-architecture.md .project-toolkit/architecture/ADR-052-template-strategy.md` |

Maintenance: when a generator is added or removed, when a Claude-plugin manifest appears or leaves, or when a drift gate moves, update `GATES` in `generator_inventory.py` and the Phase 4 table, then rerun the drift command.
