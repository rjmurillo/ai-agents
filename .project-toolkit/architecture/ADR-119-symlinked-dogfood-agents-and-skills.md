---
id: ADR-119
status: proposed
date: 2026-10-17
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
review-by: 2027-04-17
---

# ADR-119: Symlink the Agent and Skill Dogfood Trees to the Plugin Tree

## Status

Proposed. This record amends ADR-109 and ADR-108; see Related Decisions.

## Context

ADR-109 renders every shipped artifact into a plugin tree under `src/claude/`. A binplace step then copies that tree byte for byte into `.claude/`, the tree this repository loads for its own sessions. The copy is how the repository dogfoods what it ships.

For agents and skills, the copy had two costs.

1. **Two copies could disagree.** `.claude/agents/<name>.md` and `src/claude/agents/<name>.md` held the same bytes in two places. A missed `build_all.py` run left them apart until `Generated Artifact Staleness` caught it.
2. **Skill support files flowed backwards.** A skill's `SKILL.md` rendered into `src/claude/skills/<name>/` and was copied to `.claude/`. Its scripts, references, and tests went the other way: hand-maintained under `.claude/skills/<name>/`, mirrored into `src/claude/` by `sync_claude_plugin_skill_support`. One directory had two owners.

At commit `28eb90c9e` (2026-10-17), `.claude/skills/` held 104 shipped skill directories with 649 tracked files, and `.claude/agents/` held 30 agent files. All 679 were byte-identical second copies of `src/claude/` files.

The owner directed on 2026-10-17: stop copying the dogfood agents and skills; symlink them back to `src/` so they can never be out of date.

## Decision Drivers

Ranked.

1. One source of truth: an edit lands in exactly one file.
2. Harness parity: Claude Code must load the linked agents and skills exactly as it loaded the copies.
3. Containment (CWE-22, CWE-59): no link may carry a write or a trust decision outside the validated tree.
4. Dogfood fidelity: the repository should run the shipped plugin layout, so a shipped defect shows up here first.
5. Windows contributors can still check out and build.
6. Reversibility.

## Decision

1. A binplace manifest row may set `link: true` (`templates/platforms/binplace.yaml`). For such a row, binplace makes each top-level entry of `plugin_tree` a relative symlink of the same name under `install_tree`, and copies no bytes. `build/scripts/binplace_links.py` implements it.
2. The `agents` and `skills` rows set `link: true`. `.claude/agents/<name>.md` links to `../../src/claude/agents/<name>.md`. `.claude/skills/<name>` links to `../../src/claude/skills/<name>` for each shipped skill.
3. A shipped skill's support files are hand-maintained in `src/claude/skills/<name>/`. `SKILL.md` still renders from `templates/skills/<name>.SKILL.md.tmpl`.
4. A repo-local skill (`metadata.distribution: repo-local`) has no plugin copy. It stays a real directory under `.claude/skills/<name>/`, and binplace never links it.
5. The `.claude/`-to-`src/` support-file mirror is retired. `sync_claude_plugin_skill_support` now only removes a stale plugin copy of a skill that became repo-local. It refuses while `.claude/skills/<name>` is still a link, because the plugin copy is then the only copy. The function is now named `prune_stale_claude_skill_support`.
6. The `skills-sidecar` row's `install_tree` is null, since `.claude/skills/review/` is a link.
7. Codex loads the shipped Codex skills the same way. A `skills-codex` row links each `.agents/skills/<name>` to `../../src/codex/skills/<name>`; Codex loads repository skills from `.agents/skills`. Repo-local skills have no `src/codex` copy, so they stay Claude-only. `.agents/skills` is the only `.agents/` path binplace may write, and only the binplace manifest, `binplace.yaml`, and `surface-parity.yaml` may name it (`scripts/validation/agents_install_roots.py`, read by `check_agents_write_targets.py`).
8. `.claude/agents/` leaves `build_all.OWNED_PREFIXES`. It holds only links, and the `--check` snapshot refuses a symlink under an owned prefix. Its content lives under `src/`, which stays owned.

Two sub-decisions follow from these, because without them the dogfood breaks.

9. **The portability helper moves to the plugin tree.** Skill scripts find `lib/` beside their real path, which is now `src/claude/lib/`. That directory lacked `paths.py`, so the shipped Claude plugin lacked it too. `src/claude/lib/paths.py` becomes canonical. A `lib-paths` row copies it to `.claude/lib/paths.py`, and Hermes packs gain it (`lib_render.PLUGIN_LIB_FILES`).
10. **The PR completion gate trusts base-pinned links.** `run_completion_gate.py` refused any symlinked path component, so every `.claude/skills/...` command in `pr-review-config.yaml` halted. The gate now follows a link only when the trusted remote-tracking ref holds the same mode `120000` entry, at the same path under the git toplevel, with identical link text. It keeps scanning the target, so an unpinned link behind a pinned one still halts. A link with absolute text, a link that leaves the work tree, and a chain longer than eight hops halt. The owner chose this design on 2026-10-17.

The owner added one more on 2026-10-17, after asking why `.github/` differed from what ships.

11. **GitHub Copilot runs the shipped agents and hook file.** `.github/agents/<name>.agent.md` links to `../../src/copilot-cli/agents/<name>.agent.md` (`agents-github` row), and `.github/hooks/hooks.json` links to `../../src/copilot-cli/hooks/hooks.json` (`hooks-github` row, now `link: true`). `templates/platforms/github.yaml`, which rendered a second, unpinned agent variant, is deleted. The owner directed on 2026-10-17 to drop the `code-reviewer` model pin, the only difference between the two renders. `.github/agents` is inherit-only (PR #5040: an unrecognized `model:` value silently falls back to the session default, issue #4938), so the repository was not running what it ships. The directive removed the pin on every harness, Claude included. No shipped Copilot agent may now carry `model:`; `test_github_agents_link_to_shipped_copilot_agents_without_a_model_pin` enforces it. `.github/agents/`, `.github/hooks/` leave `OWNED_PREFIXES` for the same reason `.claude/agents/` did. `pr-comment-responder.prompt.md`, `security/`, and `memory-recall.json` stay hand-maintained real files.
12. **Shipped instructions plus repo-only instructions, merged at `.github/instructions/`.** The owner directed on 2026-10-17: "We may have additional instructions for THIS REPO ONLY in addition to the set that we ship ... Don't drop, merge at .github/." Each shipped `src/copilot-cli/instructions/*.instructions.md` links into `.github/instructions/` (`instructions-github` row). A rule whose scope is internal end to end is repo-only: it still skips every shipped tree, and `generate_rules.py` renders it into `.github/instructions/` as a real file (`repoOnlyOutputDirs`). The link serves the shipped file unchanged, internal globs filtered (issue #4317), so the in-repo Copilot agent runs exactly what consumers run. A repo-only instruction must start at `templates/rules/<name>.md`; `generate_rules.py` prunes any other real file in `.github/instructions/`.
13. **Repo-only rules stay in `.claude/rules/`; shipped rules are links.** The owner asked on 2026-10-17 why rules and instructions should not split like skills, where `ai-agents-*` skills are repo-local. Each shipped `src/claude/rules/<name>.md` links into `.claude/rules/` (`rules` row, `link: true`). A rule whose scope is internal end to end (`build/scripts/rule_distribution.py`, `is_repo_only`) renders straight to `.claude/rules/<name>.md` as a real file and leaves `src/claude/rules/`, the way a repo-local skill's `SKILL.md` renders into its real `.claude/skills/<name>/`. Six rules are repo-only at `60a2d6f06` (2026-10-17): `adr-records`, `governance`, `push-lock`, `secret-redaction`, `session-logs`, `tool-use-hook-bar`. `generate_rules.py` reads those real files too (`repoOnlySourceDir`), so `.github/instructions/` still gets them. The scope decides, as the Copilot skip has since issue #4317, so one classifier serves both trees. A consumer may have `.claude/`, but these rules cite only this repository's internals. A scope edit can move a rule in or out of the plugin, so `tests/build_scripts/test_rule_distribution.py` pins the six names and fails until the edit is deliberate. A rule that flips from shipped to repo-only replaces its own binplace link on the next build; any other symlink at that path is refused.
14. **`.claude/lib` entries link into `src/claude/lib`.** `.claude/lib/{github_core,hook_utilities,ai_review_common}`, `bootstrap.py`, and `paths.py` were byte copies of `src/claude/lib`, so a verifier that imported `.claude/lib` through `abspath(__file__)` beside a link could load a copy that disagreed with the shipped one the diff changed. The owner reported that the PR completion gate had several bypasses of this shape. A new `lib` row (`link: true`, `plugin_tree: src/claude/lib`, `install_tree: .claude/lib`) links each of the five entries to `../../src/claude/lib/<name>`. The five `lib-*` rows keep compiling into the plugin trees and drop their `install_tree` (null), the way `skills-sidecar` did in decision 6. The eight hand-maintained modules with no `src/claude/lib` counterpart (`claude_hook_dispatch.py`, `claude_hook_protocol.py`, `hook_dispatch.py`, `hook_dispatch_protocol.py`, `hook_dispatch_timeout.py`, `output_capture.py`, `qa_report.py`, `shim_loader.py`) stay real files; `binplace_manifest.REPO_LOCAL_LIB_NAMES` is the `skip_names` set for the row, and a test fails if a name on that list starts to ship. `.claude/lib/` leaves `build_all.OWNED_PREFIXES`, as `.claude/agents/` did in decision 8. The two `CLAUDE.md` claude-mem stubs under `.claude/lib/github_core/` and `.claude/lib/hook_utilities/` are deleted: each had no counterpart in the plugin tree and held only an empty auto-generated block (`scripts/github_core/CLAUDE.md` and `scripts/hook_utilities/CLAUDE.md` still exist). `CODEOWNERS` pins each link by name without a trailing slash, because a directory pattern does not match a link entry.

## Rationale

Drivers 1 and 4 decide the mechanism: a link has no second copy to go stale, and it makes this repository execute `src/claude/` exactly as an installed plugin does. Decision 9 is that driver paying off: the link exposed that the shipped Claude plugin had no `paths.py`.

Decision 7 applies drivers 1 and 4 to `src/codex/`. Driver 2 is met by measurement for both Claude Code and Codex (Prior Art). Driver 3 shapes decisions 1, 5, and 10: every link target is computed, never trusted from disk, and the gate trusts only links the base branch already holds. Driver 5 is met by CI configuration and a loud failure, not by a copy fallback (Consequences). Per-entry links, not one link for `.claude/skills/`, keep repo-local skills as real directories (decision 4).

## Safety

- Every link target is computed from the validated plugin tree. A link on disk passes only when its text equals the computed relative target.
- A plugin entry that is itself a symlink, or resolves outside the plugin tree, is refused (exit 2), so no install link chains through the plugin tree to another place.
- Binplace replaces a real directory with a link only when every file matches the plugin entry byte for byte. Otherwise it exits 2 and names the directory, so a hand edit is never lost.
- A NO-REGEN file at a link path is skipped with exit 1, the copy path's contract.
- `build_all.py --check` reports a missing link, a wrong target, a real file or directory where a link belongs, and a stale link to a removed plugin entry. Each is drift, exit 2.
- A real file under `.claude/agents/` with no plugin twin is reported as an unowned notice, not an error, as before. Claude Code would load it. No gate fails on it, because `.claude/agents/` is no longer an owned prefix.

## Alternatives Considered

- **Keep copying (status quo).** Rejected by the owner directive: 679 duplicate files can drift.
- **ADR-109 Alternative D: symlink all of `.claude/` to `src/claude/`.** ADR-109 rejected it for two reasons. (a) Containment: `--check` refused symlinked owned paths. This record removes `.claude/agents/` from the owned prefixes, keeps the `src/` content owned, moves the skill existence check to the real `src/claude/skills/<name>/` directory, and adds per-link target checks. (b) Portability: Windows checkouts and some installers do not preserve links. This record accepts that cost for contributors, fails loud when a link cannot be made, and fixes the one installer that mishandled links (`packages/ai-agents-cli/scripts/build-bundle.ts`). Linking the whole tree is still rejected, because `.claude/` also holds repo-local skills, rules, hooks, settings, and lib modules that are not in `src/claude/`.
- **Load the plugin itself instead of a mirror** (enable `project-toolkit@ai-agents` from `.claude-plugin/marketplace.json`, or `claude --plugin-dir src/claude`). Rejected. Plugin skills load under the `project-toolkit:` namespace, so every bare skill name in hooks, rules, and docs would change. An installed plugin runs from a cached copy that goes stale until reinstalled. `--plugin-dir` must be passed on every session. Copilot CLI, which reads `.claude/skills/` in this repository, gains nothing from either.
- **One link for all of `.claude/agents/`.** Rejected: per-entry links keep one code path for both rows, and a stray file in `.claude/agents/` stays visible as unowned instead of landing in the plugin tree.
- **Keep a separate unpinned `.github/agents` render.** Rejected by the owner on 2026-10-17: it meant the repository's Copilot agents differed from the shipped ones. Dropping the one pin (`code-reviewer`, `model_tier: haiku`) made the renders identical.
- **Keep the `code-reviewer` pin and link the other 29 agents.** Rejected: a mixed tree, and the pinned agent would still differ from what GitHub runs.
- **Drop the pin from the Copilot projections only and keep the Claude `haiku` pin** (ADR-111 rule 3 style). Rejected by the owner directive, which named no harness.
- **Link all of `.github/instructions/` to `src/copilot-cli/instructions/`.** Rejected: one directory link leaves no room for the repo-only rules. Per-entry links do (decisions 12 and 13).
- **Keep internal globs in the shipped Copilot tree, so the linked copies keep them in this repository.** Rejected in review: it would widen 11 shipped rules to consumers' own `.claude/`, `.agents/`, and `.project-toolkit/` trees, reversing issue #4317 for Copilot.
- **Declare repo-only status with a frontmatter marker, as skills do.** Deferred: the scope already decides the Copilot skip, so a marker would add a second classifier that can disagree with it. The pinned-set test makes a flip a reviewed edit.
- **Keep shipping the six repo-only rules in the Claude plugin.** Rejected: Copilot already skipped them, their scopes name only this repository's internal trees, and a repo-only skill already stays out of the plugin.
- **Leave Codex on the marketplace entry only.** Rejected: `.agents/plugins/marketplace.json` sources `./src/codex`, but a marketplace plugin loads only once installed, from a cached copy. Linking `.agents/skills/` makes every Codex session in this repository run `src/codex` directly.
- **Link `.github/instructions/` to the shipped set and drop the repo-only rules.** Rejected by the owner: the in-repo Copilot agent would lose the six repo-only rules. The loss of internal globs on eleven shipped rules was also listed against it; the chosen design keeps that loss. The owner accepted it on 2026-10-17 (D4, "Filtered links") so consumers see no scope change.
- **Keep `.github/instructions/` as its own render.** Rejected by the owner: it differed from what ships.

## Prior Art Investigation

The copy existed because ADR-108 and ADR-109 built the template pipeline on a `.claude/` tree that was then the hand-maintained source, and ADR-109 Alternative D found the containment checks would refuse links. Those checks still exist and are adapted, not removed (Safety).

`memory_enhancement` at the repository root is a tracked symlink to `scripts/memory_enhancement` (git mode `120000`); `scripts/validation/tracked_paths.py` already resolves paths through tracked links.

Copilot CLI loading of a linked skill directory in this checkout is unverified and accepted; the shipped Copilot plugin (`src/copilot-cli/`) holds no links. Copilot CLI 1.0.98 loads a symlinked `.github/agents/<name>.agent.md`: in a scratch repository it listed the probe agent through the link and listed none without it. A linked repository hook file is unverified: in the same probe a hook did not fire from a real file either, likely because the scratch folder was not trusted, so the probe could not discriminate; `hooks.json` registers no hook today. Codex CLI 0.163.0 loads a symlinked `.agents/skills/<name>`: in a scratch repository it listed the probe skill through the link and listed none without it, and in this repository it reports `chestertons-fence` available and an invented name unavailable. Claude Code 2.1.302 loads a symlinked skill directory and a symlinked agent file. Probe on 2026-10-17 in a scratch repository: with `.claude/skills/zebra-probe` and `.claude/agents/walrus-probe.md` as relative links into `src/claude/`, `claude -p` listed both. Negative control: with the links removed, it listed neither.

## Consequences

### Positive

- An agent or skill edit lands in one place. `.claude/` cannot hold stale agent or skill content.
- 679 duplicate tracked files leave the tree: 649 skill files are deleted and 30 agent files become links, for 134 new link entries under `.claude/agents` and `.claude/skills` (135 in the index with `memory_enhancement`). The 679 count describes the pre-conversion tree at `28eb90c9e` (2026-10-17): 649 shipped skill files and 30 agent files. Link counts come from `git ls-tree -r 5d69fdbd8 | awk '$1=="120000"'` (2026-10-18). They are 30 in `.claude/agents`, 104 in `.claude/skills`, 23 in `.claude/rules`, 104 in `.agents/skills`, 30 in `.github/agents`, 23 in `.github/instructions`, 1 in `.github/hooks`, and 1 for `memory_enhancement`. That is 316 links in all. `.claude/skills/` keeps 121 entries: 104 shipped links and 17 repo-local directories.
- The dogfood now runs the shipped layout. It surfaced and fixed three shipped defects: the Claude plugin had no `lib/paths.py`, the npm bundler dropped linked skills (92 files bundled instead of 642), and several scanners counted both copies.

### Negative

- **Git paths.** Git refuses a path beyond a symlink: `git add .claude/skills/adr-review/SKILL.md` fails with `pathspec ... is beyond a symbolic link`. Editing through `.claude/` works; git commands must name `src/claude/skills/...`. Rule and guide text now names `src/claude/skills/<name>/` as the edit location.
- **Resolved paths.** `Path(__file__).resolve()` in a skill script now lands under `src/claude/skills/`, one directory deeper, and its sibling `lib/` is `src/claude/lib/`.
- **Enumerators.** `Path.rglob`, `os.walk`, and `git ls-files` do not descend into a linked directory. A gate that enumerated `.claude/skills` silently scanned only repo-local skills until it was pointed at `src/claude/skills`.
- **CI path filters.** A support-file edit appears in a diff only under `src/claude/`. Filters, `labeler.yml`, `CODEOWNERS`, and `scripts/ci/path_policy.yml` now name `src/claude/skills` or `src/claude/agents` beside each `.claude/` pattern.
- **Windows.** A checkout needs `core.symlinks=true` and symlink privilege (Developer Mode). Without them git writes each link as a text file holding its target, including `.github/agents/*.agent.md`, `.github/hooks/hooks.json`, and `.agents/skills/*`, and `build_all.py --check` reports drift. Creating a link without privilege exits 2 with a message naming both settings. The two Windows CI jobs that read `.claude/` (`cli-smoke.yml`, the `test-windows-pwsh` job in `pytest.yml`) set `core.symlinks` before checkout.
- **Gate transition window.** Decision 10 pins links from the trusted ref. Until a new link reaches `origin/main`, the completion gate halts for any criterion that reaches it through `.claude/`. That includes the PR that introduces this record, and any PR that adds a skill or agent. Remedies: pass `--config src/claude/skills/pr-review/pr-review-config.yaml` (byte-identical at the base), or record the reviewed one-time override. Fetch `origin` after the merge.
- **Known gate debt.** The completion gate's module and dynamic-load resolvers do not all return the post-link path. A criterion that imports through a pinned link can halt as untrusted. This fails closed, so the cost is a false halt, not a bypass.
- **Coverage.** `coverage.py` records the real path, so `src/claude` joins `[tool.coverage.run] source`, and the REQ-009 gate's `--include` names the `src/claude/skills/...` path.

- **Codex skill links point at generated files.** `src/codex/skills/` renders from `src/claude/skills/`, so an edit made through `.agents/skills/<name>/` is overwritten by the next build. Edit `src/claude/skills/` (support files) or `templates/skills/` (`SKILL.md`).
- **Codex lists a skill twice when the plugin is also enabled.** With `project-toolkit@ai-agents` enabled, Codex 0.163.0 in this repository lists `chestertons-fence` (the repository link) and `project-toolkit:chestertons-fence` (the plugin's cached copy). The names differ, so nothing collides; the bare name runs `src/codex` directly. Disable the plugin in this checkout to see one copy. Whether Copilot CLI or VS Code also scans `.agents/skills`, and would list a second render beside `.claude/skills`, is unverified.
- **`.agents/skills` has no snapshot guard.** `build_all.assert_no_claude_writes` covers `.claude/` only. `binplace_links.py` alone governs `.agents/skills`, with the same computed-target and symlinked-entry checks.
- `.agents/skills` gains 104 link entries (mode `120000`), one per `src/codex/skills` directory.

- **No Copilot agent may pin a model.** `.github/agents/` serves the shipped files, and `.github/agents` is inherit-only (PR #5040: an unrecognized `model:` value silently falls back to the session default, issue #4938); `check_model_pins.py` scans `.github/agents/*.md` through the links. ADR-111 rule 2 (KEEP_PIN) and rule 3 (bare `haiku`) now bind Claude agents only; the `copilot-cli.yaml` `model_tiers` fallback must not emit an agent pin. The `code-reviewer` agent now runs on each harness's default model instead of the Haiku tier; Claude, Copilot CLI, and VS Code renders all lost the pin.
- **`.github/hooks/hooks.json` loading through a link is unverified** on Copilot CLI and the cloud agent. It registers nothing today; a test keeps its `hooks` map empty until a link-loading probe is recorded.
- **Linked `.github/agents` on the github.com cloud agent and in VS Code are unverified.** Only Copilot CLI 1.0.98 was probed. After merge, list the custom agents in a cloud-agent session; Reversibility step 4 is the rollback if they are missing.
- **The Claude plugin ships 23 rules, not 29, at `60a2d6f06` (2026-10-17).** The six repo-only rules leave `src/claude/rules/` (decision 13). A consumer with `.claude/` could have matched `push-lock` or `tool-use-hook-bar`, but their text governs this repository's hooks and push lock. The Copilot plugin already skipped all six.
- **The in-repo Copilot agent loses internal scopes on 11 shipped rules.** `.github/instructions/` used to keep `.claude/**` and `.agents/**` globs on rules such as `canonical-source-mirror` and `generated-artifacts` (11 at `60a2d6f06`, 2026-10-17). The links now serve the shipped, filtered scope, so editing a `.claude/` path no longer auto-loads them for Copilot. Claude Code reads `.claude/rules/`, which keeps every glob.
- **Linked `.github/instructions` on the github.com cloud agent and in VS Code are unverified**, like `.github/agents`. Reversibility step 5 is the rollback.
- **Edit a repo-only rule at its template.** `rule_templates.py` renders it to `.claude/rules/<name>.md`; `--check` owns that real file, and the lossless fixture compares against it.
- **Cost.** `code-reviewer` moves from the Haiku tier to each harness's default model on every call. A later owner decision could restore a Claude-only pin, since the Copilot constraint does not reach `src/claude/`.
- **`.claude/lib` links behave like the skill links.** Git refuses a path beyond a link, so `git add .claude/lib/github_core/api.py` fails; name `src/claude/lib/github_core/api.py`. `Path(__file__).resolve()` in a module loaded through `.claude/lib` lands in `src/claude/lib/`, so `paths.py` reports `src/claude` as its plugin root. Decision 10 also governs these links: until they reach `origin/main`, the completion gate halts a criterion that imports through `.claude/lib`. The remedy is the decision 10 override, owned by the PR author and spent when the merge lands.
- **Windows without `core.symlinks`.** Git writes the five links as text files, so every hook that imports `github_core` or `hook_utilities` fails at import and `build_all.py --check` reports drift. The two Windows CI jobs already set `core.symlinks`; a contributor checkout needs the same setting and Developer Mode.
- **Nested links are unguarded by binplace.** `binplace_links.py` checks only top-level plugin entries, so `test_plugin_lib_tree_holds_no_symlinks` pins that `src/claude/lib` holds none. CODEOWNERS on `/src/claude/lib/` carries the review.
- **Two tracked file links.** `.claude/lib/bootstrap.py` and `.claude/lib/paths.py` are file links, the first in the tree. Scanners that read every tracked `.py` must skip a link and read its target once (`subprocess_encoding_count_ratchet.py`).
- **Hand-maintained neighbours.** Eight modules stay real files in `.claude/lib/`. A new top-level module there is real by default; a new `src/claude/lib` entry is linked on the next build, and a real file of the same name is replaced by the link in write mode (a real directory whose bytes differ is refused, exit 2), and `--check` reports it as drift.

### Neutral

- `.claude/hooks/` remains a byte copy. The same `link: true` flag can cover it in a later change.

## Impact on Dependent Components

- `build/scripts/binplace_manifest.py`: reads `link`, folds link outcomes into `BinplaceResult`, allowlists link paths, and on a copy row unlinks a leftover top-level install link (rollback).
- `build/scripts/skill_templates.py`: a shipped skill's existence check moves to `src/claude/skills/<name>/`; `owned_targets` returns only the path `compile_all` writes.
- `build/scripts/skill_support_mirror.py`: the copy mirror is removed.
- `build/scripts/build_all.py`: `.claude/agents/` leaves `OWNED_PREFIXES`.
- `build/scripts/lib_render.py`: Hermes packs include `paths.py`.
- `build/scripts/check_surface_parity.py`: a binplace row whose `source` is its `plugin_tree` may describe that tree as `independent`.
- `scripts/validation/check_agents_write_targets.py` with `agents_install_roots.py`: `.agents/skills` was the retired #5421 path; its install-root owners may now name it, and every other file still may not.
- `templates/platforms/github.yaml`: deleted. `build/generate_agents.py` no longer allows an output directory outside `src/`, so no platform can write through the `.github/agents` links. `build/sync_slim_agents.py` names `src/copilot-cli/agents` instead of `.github/agents`.
- `templates/agents/code-reviewer.{claude.md.tmpl,copilot.md.tmpl,shared.md}`: the model pin is removed (decision 11).
- `templates/platforms/binplace.yaml` `skills-codex` row and `templates/platforms/surface-parity.yaml` `skills-codex-install` surface: decision 7.
- `templates/platforms/copilot-cli.yaml` and `codex.yaml`: `sourceDir` reads `src/claude/skills`, the real directory.
- `src/claude/skills/github/scripts/pr/run_completion_gate.py`: decision 10.
- `packages/ai-agents-cli/scripts/build-bundle.ts`: follows links when it bundles `.claude/`.
- Repository scanners and ratchets that enumerated `.claude/skills` scan `src/claude/skills` once. Several counted both copies before, so their baselines moved down only.
- `scripts/validation/adr_cited_paths.py`: a cited path under a tracked link exists when its target is tracked.
- `build/scripts/rule_distribution.py` (new), `rule_templates.py`, `generate_rules.py` (`repoOnlySourceDir`, `repoOnlyOutputDirs`), `validate_templates_schema.py`, and REQ-003 (dated notes on REQ-003-006 and REQ-003-010): decisions 12 and 13. `build_all.py` must compile rules before `generate_rules.py` reads `.claude/rules/`; it already does.
- `binplace.yaml` `rules` and `instructions-github` rows; `build_all.py`: `.claude/rules/` and `.github/instructions/` leave `OWNED_PREFIXES`, and their real repo-only files are owned one by one.
- `scripts/eval/eval-rule-activation.py`, `scripts/validation/checks_portability.py`: accept a rule that resolves into `src/claude/rules/` or a repo-only real file.
- `binplace.yaml`: new `lib` row; the five claude-side `lib-*` rows set `install_tree: null`. `binplace_manifest.py`: `REPO_LOCAL_LIB_NAMES` and its use in `_repo_local_names`. `build_all.py`: `.claude/lib/` leaves `OWNED_PREFIXES`.
- `templates/platforms/surface-parity.yaml`: `lib-claude-plugin` and `lib-claude-install` replace the five per-entry install surfaces and the two per-package guide surfaces.
- `scripts/validation/check_unreachable_code.py` and the pre-push semgrep scan in `git_hook_policy.py` (`_commit_link_paths`): skip a tracked file link and scan its target, since both refused a non-regular file.
- `scripts/ci/subprocess_encoding_count_ratchet.py`: skips a tracked file link only when its target is tracked. `scripts/ci/type_ignore_count_ratchet.py`: comment only; its `.claude/lib` prefix stays harmless. `.github/CODEOWNERS`: link entries pinned by name.
- Guides and context files that called `.claude/lib` a copy now call it a link: `.claude/AGENTS.md`, `build/AGENTS.md`, `.claude/hooks/AGENTS.md`, `GENERATOR-FILES.md`, the `generated-artifacts` and `plugin-self-containment` rule templates.

## Reversibility Assessment

Reversible in one change set, with these steps.

1. Remove `link: true` from the `agents` and `skills` rows and run `build_all.py`. The copy path unlinks each leftover top-level install link, then copies real files; `--check` reports any link it finds on a copy row as drift (`test_dropping_link_true_restores_real_directories`).
2. Restore from history: the support-file mirror in `skill_support_mirror.py`, `.claude/agents/` in `OWNED_PREFIXES`, the `skills-sidecar` install tree, the `.claude/skills/<name>/` existence check in `skill_templates.py`, the `sourceDir` values in `copilot-cli.yaml` and `codex.yaml`, and the scanner roots and baselines.
3. Remove the `skills-codex` row, the `skills-codex-install` surface, `_CODEX_SKILLS_ROOT` in `binplace_manifest.py`, `scripts/validation/agents_install_roots.py` and its use in `check_agents_write_targets.py`, and their tests; then `git rm` the `.agents/skills` links. Nothing copies there.
4. For decision 11: restore `templates/platforms/github.yaml` and its allowlist entry in `generate_agents.py`, delete the `agents-github` row, drop `link: true` from `hooks-github`, return `.github/agents/` and `.github/hooks/` to `OWNED_PREFIXES`, and restore the `code-reviewer` pin if wanted.
5. For decisions 12 and 13: drop `link: true` from the `rules` row, delete the `instructions-github` row, drop the `repoOnly*` keys, point `render_target` at `src/claude/rules/` for every rule, and return both trees to `OWNED_PREFIXES`. Delete the six real files in `.claude/rules/` and `.github/instructions/` before the first copy run; the build then renders all 29 rules to `src/claude/rules/`.
6. Decision 10 and decision 9 may stay: with no links, the gate meets no link, and `src/claude/lib/paths.py` fixes the shipped plugin regardless.
7. For decision 14: delete the `lib` row, restore each claude-side `lib-*` row's `install_tree` (`.claude/lib/<name>`), return `.claude/lib/` to `OWNED_PREFIXES`, restore the five per-entry install surfaces and the two per-package guide surfaces in `surface-parity.yaml`, and run `build_all.py`. The copy path unlinks each leftover top-level link and copies real files, and `--check` reports a link on a copy row as drift. Restore the two `CLAUDE.md` stubs from history only if wanted.

## Related Decisions

- ADR-109 (template-first plugin distribution): amended. Its Alternative D is adopted for agents and skills, and its 2026-09-15 support-file amendment is retired for shipped skills. Both carry a dated note pointing here.
- ADR-108 (template-owned skill files): amended. The not-a-symlink existence check applies to `src/claude/skills/<name>/` for shipped skills. It carries a dated note pointing here.
- ADR-052: superseded by ADR-109; unchanged.
- ADR-111 and ADR-080 (model pins): amended by decision 11. Copilot agent pins are forbidden; both carry a dated note pointing here.
- ADR-012 (proposed): reserves `.agents/skills/*.md` for learned-pattern files. Decision 7 gives `.agents/skills/` to Codex skill links instead; the owner should retire or amend ADR-012's use of the name.

## Review

Revisit by 2027-04-17, or sooner if a harness stops loading symlinked skills or agents.

## Consensus

See `.project-toolkit/critique/ADR-119-debate-log.md`; the review of decision 14 is `.project-toolkit/critique/ADR-119-debate-log-6.md`.

## References

- `build/scripts/binplace_links.py`, `templates/platforms/binplace.yaml`.
- `tests/build_scripts/test_binplace_links.py`, `tests/skills/github/test_run_completion_gate.py` (`TestPinnedLinkTrust`).
