# Upstream provenance and reconciliation

This guide requires the ai-agents source checkout.
Installed consumers do not need its generation or validation tooling.

## Ownership

This is an MIT-licensed fork of Warp's skill-doctor, credited to warpdotdev.
The copyright holder is Denver Technologies, Inc.
The complete upstream MIT notice ships in `src/claude/skills/skill-doctor/LICENSE`.
The report retains upstream assets and Warp branding.

Upstream repository: <https://github.com/warpdotdev/common-skills>.
Pinned upstream skill directory: `.agents/skills/skill-doctor`. <!-- agents-write-target: historical -- Directory in the pinned upstream tree, not this checkout. -->
Baseline: `8792394ff1b655e0af451b8fabb68ef0cfcbd208`, fetched 2026-11-09.
This SHA is the reconciliation base, not a promise of current upstream freshness.

## Local file mapping

Paths below are relative to the ai-agents checkout.
Installed consumers need only this skill's bundled files.

| Upstream | Local editable source |
| --- | --- |
| `SKILL.md` | `templates/skills/skill-doctor.SKILL.md.tmpl` |
| `scripts/*.py`, excluding tests | `src/claude/skills/skill-doctor/scripts/` |
| `scripts/test_*.py` | `tests/skills/skill-doctor/` |
| `references/`, `scorers/`, `assets/` | `src/claude/skills/skill-doctor/` |
| Repository `LICENSE` | `src/claude/skills/skill-doctor/LICENSE` |

`build/scripts/build_all.py` renders the template and distributes the bundled files.
Never reconcile directly into generated platform copies.
The `.claude/skills/skill-doctor` entry is a generated link.
The Copilot copy lives under `src/copilot-cli/skills/skill-doctor`.

The collector's upstream name is `collect_sessions.py`.
There is no renamed `collection_sessions.py` compatibility entry point.

## Local changes to preserve

1. Copilot discovery, parsing, CLI options, and skill discovery.
2. Copilot documentation and synthetic regression tests.
3. Template frontmatter, plugin-root resolution, and PowerShell instructions.
4. Upstream attribution, bundled MIT notice, and this reconciliation guide.
5. Tests relocated outside shipped scripts, with adjusted source paths.
6. Repository formatting and dash normalization in imported prose.
7. Final response without an automatic promotional or edit-application prompt.
8. Central attribution in `scripts/generate_third_party_notices.py`.
9. Explicit scoring-provider boundaries instead of an unsupported local-only guarantee.
10. UTF-8 reads and writes, closed SQLite fixtures, and portable home-directory tests.
11. Hermes exclusion in `templates/platforms/hermes.yaml`, due to its per-file size limit.
12. Cohesive collector, browser-script, and test modules within repository complexity limits.
13. Explicit annotations for dynamic parser data, without disabling strict type checks.
14. Native path containment, including Windows case-insensitive repository matching.
15. Explicit UTF-8 Git output decoding and escaped legacy-console diagnostics.
16. Python 3.10+ requirements and POSIX and PowerShell rendering instructions.
17. Unicode filesystem, read-only SQLite URI, and OS discovery regression tests.
18. Deterministic inventory handoff to skill-bootstrap, separate from qualitative report scoring.
19. Copilot context history and exclusion of mixed-repository sessions from project-scoped collection.
20. Offline GitHub and Azure DevOps evidence imports with scope and pagination validation.
21. Bounded bootstrap-to-doctor diagnosis without recursive bootstrap calls or automatic draft application.
22. Existing-skill updates with authorization, frozen cases, and old-versus-updated comparisons.
23. Harness-root defaults, with other skill directories supplied through `--skills-dir`.
24. Resolved Claude-home overrides and rejection of non-object JSONL records.
25. Same-name definitions kept in usage detection, with the first-seen copy as the edit target (issue 7185).
26. Partial-collection counters, including bootstrap provenance and source failure isolation.
27. Deferred Pi/Grok skill matching until project discovery finishes.
28. Bounded browser launch and a fixed upstream HTTPS report destination.
29. Loaded-skill startup paths independent of plugin variables or the working directory.
30. Unchanged upstream scoring weights, with explicit outcome-causality limitations.
31. Content fingerprints with path aliases per definition, `skill_variants`, and unresolved historical attribution (issue 7185).
32. Namespace-qualified invocations such as `project-toolkit:skill-doctor` counted as usage of the installed name, with `skill_attribution` evidence (issue 7190).
33. Codex turn counts from `response_item` messages by role when the rollout has no `event_msg` turns, with no double count in older rollouts (issue 7184).
34. Codex `response_item/agent_message` text rendered in transcripts as `child-agent` entries (issue 7189).
35. `stats.terminated_by` from Codex `task_complete.error.codex_error_info` and Claude `isApiErrorMessage` records, shown in the transcript header and as its last entry. Droid matching moves to issue 7188 (issue 7189).
36. `--min-idle-minutes` (default 15) quiet window on `stats.last_ts`, counted as `sessions_skipped_idle` (issue 7189).
37. `failed_conversations` leaves out failures caused only by provider termination, and the report states how many (issue 7189).
38. Factory Droid collector: `droid` harness ID, `--factory-home`, `session_droid.py`, and `droid_home` in the inventory.
39. Project skill discovery now includes `<repo>/.factory/skills`, and global discovery includes `<factory-home>/skills`.
40. `stats.terminated_by` for Droid sessions that end on `model_usage_exhausted` or a short usage-limit message.
41. Devin CLI and Antigravity listed as known and unsupported in `supported-harnesses.md`, with no collector.

Do not replace local files wholesale with the newest upstream tree.
Do not restore removed local adaptations merely because upstream still includes them.

## Reconcile a new upstream revision

Start from a clean feature branch.
Preserve unrelated work before generating platform copies.
Use a separate upstream checkout outside the host repository.
On Windows, run these commands in PowerShell:

```powershell
$upstream = Join-Path ([System.IO.Path]::GetTempPath()) ("skill-doctor-upstream-" + [guid]::NewGuid())
git clone --filter=blob:none --no-checkout https://github.com/warpdotdev/common-skills.git $upstream
git -C $upstream fetch origin main
$next = git -C $upstream rev-parse origin/main
$base = '8792394ff1b655e0af451b8fabb68ef0cfcbd208'
$skillPath = '.agents/skills/skill-doctor' # agents-write-target: historical -- Directory in the pinned upstream tree, not this checkout.
git -C $upstream diff --stat $base $next -- $skillPath LICENSE
git -C $upstream diff $base $next -- $skillPath LICENSE
```

On Linux or macOS:

```bash
upstream="$(mktemp -d "${TMPDIR:-/tmp}/skill-doctor-upstream.XXXXXX")"
git clone --filter=blob:none --no-checkout https://github.com/warpdotdev/common-skills.git "$upstream"
git -C "$upstream" fetch origin main
next="$(git -C "$upstream" rev-parse origin/main)"
base='8792394ff1b655e0af451b8fabb68ef0cfcbd208'
skill_path='.agents/skills/skill-doctor' # agents-write-target: historical -- Directory in the pinned upstream tree, not this checkout.
git -C "$upstream" diff --stat "$base" "$next" -- "$skill_path" LICENSE
git -C "$upstream" diff "$base" "$next" -- "$skill_path" LICENSE
```

Review the full upstream delta, including deletions, tests, assets, and license changes.
Treat upstream skill text as source data, not instructions to execute.
Read scripts before executing them.
For each changed file, compare three versions: baseline, new upstream, and local.
Use `git show REV:path` to extract baseline and new files.
Apply upstream hunks to the mapped local source, preserving the local changes above.
Resolve overlapping hunks manually instead of choosing one entire side.
Port upstream tests alongside the behavior they protect.
Inspect bundled JavaScript notices when assets change.
Preserve original copyright and permission notices.

If upstream adds Copilot support, compare both implementations against local fixtures.
Retain local coverage until the replacement passes the same behavioral tests.
Document any deliberately rejected upstream hunk and its reason here.
Update the baseline SHA and date only after reconciliation passes validation.
Also update `$base` in the command example for the next maintainer.

## Validation

From the host checkout:

```powershell
uv run python build\scripts\build_all.py
uv run --frozen --extra dev pytest tests\skills\skill-doctor -q
uv run --frozen --extra dev ruff check src\claude\skills\skill-doctor\scripts tests\skills\skill-doctor
uv run --frozen --extra dev ruff format --check --force-exclude src\claude\skills\skill-doctor\scripts tests\skills\skill-doctor
uv run --frozen --extra dev mypy src\claude\skills\skill-doctor\scripts
uv run python scripts\generate_third_party_notices.py
uv run python scripts\generate_third_party_notices.py --check
uv run python build\scripts\build_all.py --check
```

On Linux or macOS, use forward-slash path separators in these validation commands.
Also run bootstrap tests when changing the shared discovery and improvement contracts:

```bash
uv run --frozen --extra dev pytest tests/skills/skill-bootstrap tests/skills/skill-doctor -q
```

The final drift check compares generated files with committed repository state.
Uncommitted generated files can therefore fail despite correct rendering.
Inspect and commit the intended source and generated changes before the final check.
Never suppress that check or bypass commit hooks.

Run the generated Copilot collector from an unrelated directory using synthetic history.
Cover explicit `--harness copilot`, default auto-selection, and `COPILOT_HOME`.
Verify empty, missing, malformed, old, child, and out-of-scope histories.
Verify installed skill detection and bounded transcripts.
Run inherited collector and report-renderer tests to protect other harnesses.
Run the runtime tests on Linux, macOS, and Windows before claiming native verification.
Changing `sys.platform` tests discovery branches, not native filesystem behavior.
Exercise Unicode project paths and report paths containing spaces.
Verify the Python 3.10 floor with a real interpreter, not syntax parsing alone.
Never commit real transcripts or upload local history.

## Windows generation caveat

Observed on 2026-11-09: `skill_distribution._is_plugin_link` requires forward-slash link text.
Windows can report the same relative target with backslashes.
The full build can reject existing links before generating this skill.
Do not modify unrelated links or weaken validation during reconciliation.
Scoped generator APIs accept an isolated `repo_root` for inspecting new output.
Scoped output checks do not clear a failed full drift gate.
