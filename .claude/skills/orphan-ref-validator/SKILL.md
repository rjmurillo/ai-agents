---
name: orphan-ref-validator
version: 1.0.0
description: Detect references to skills and scripts in structured artifacts (specs, ADRs, eval fixtures, plugin manifests, skill descriptions) that do not match working-tree state. Run as a /build Mandatory Exit Gate to block orphan refs pre-commit instead of paying iteration rounds in /pr-quality:all post-PR.
license: MIT
---

# orphan-ref-validator

## Purpose

Scans structured artifacts (specs, ADRs, eval fixtures, plugin manifests, skill descriptions) for references to entities that do not exist in the working tree:

- **Skill names** that no longer have a `.claude/skills/<name>/` directory. Emitted as `Finding(kind="skill_name", severity="critical")`.
- **Script paths** under `build/scripts/`, `scripts/validation/`, `scripts/`, or `tests/` that are not present on disk. Emitted as `Finding(kind="script_path", severity="critical")`.
- **Rule and instruction paths** under `.claude/rules/`, `.github/instructions/`, or `src/copilot-cli/instructions/` that are not present on disk. Emitted as `Finding(kind="rule_path" | "instruction_path", severity="critical")`.

Emits findings per the ADR-056 envelope and a final verdict line. Exit code follows ADR-035: `VERDICT: PASS` or `VERDICT: WARN` exits `0`; `VERDICT: CRITICAL_FAIL` exits `1`; usage/configuration or incomplete scan exits `2`; external failures exit `3`; permission failures exit `4`.

The skill ships with vendored installs. Missing targets are errors by default. Use `--allow-missing-targets` only when the caller intentionally runs in a partial vendored tree, and use `--allow-empty-scan` only when zero scanned files is the declared scope.

## Triggers

| Trigger | Effect |
|---|---|
| `scan for orphan refs` | Run with default targets |
| `validate orphan references` | Run on a specific path |
| `check skill catalog drift` | Run with default targets |
| `build mandatory exit gate` | Invoked by the build lifecycle command |

## Path conventions

Absolute paths in this document (e.g. `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py`) assume the canonical Claude install layout under `.claude/`. The Copilot CLI mirror at `src/copilot-cli/skills/orphan-ref-validator/scripts/scan.py` is byte-identical Python; on Copilot CLI, replace `.claude/` with the install root the platform uses. The `Skill(skill="orphan-ref-validator")` invocation form is platform-agnostic and is what the `/build` gate uses.

## Inputs

```text
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
    [--targets PATH ...] \
    [--include-adrs] \
    [--include-skill-descriptions] \
    [--allow-missing-targets] \
    [--allow-empty-scan] \
    [--baseline FILE] \
    [--repo-root PATH] \
    [--output {json,human}] \
    [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

| Flag | Purpose | Default |
|---|---|---|
| `--targets` | Files or directories to scan | tracked `.md`, `.json`, `.yaml`, and `.yml` files under `.agents/specs/`, `.claude/rules/`, `.github/instructions/`, `src/copilot-cli/instructions/`, and `tests/`, plus plugin manifest JSON files |
| `--include-adrs` | Add `.agents/architecture/` and `docs/` to defaults (opt-in) | off |
| `--include-skill-descriptions` | Add `.claude/skills/*/SKILL.md` to defaults (opt-in until preexisting drift is cleaned) | off |
| `--allow-missing-targets` | Treat missing targets as optional vendored-install paths | off |
| `--allow-empty-scan` | Permit `PASS` after scanning zero files | off |
| `--baseline` | Path to a file of known pre-existing finding keys (`target_file:line:kind:referenced_entity`). Matching findings are marked `suppressed` and do not fail the scan; new findings still exit `1`. Accepts a JSON list of keys, a saved scan envelope (`Data.findings`), or one key per line (`#` comments allowed). | none |
| `--repo-root` | Repository root. Walks up from CWD for the nearest `.git` directory; falls back to CWD. Validates that user-supplied paths exist and are directories (returns ADR-035 exit `2` otherwise). | walked from CWD |
| `--output` | `json` (ADR-056 envelope) or `human` (compact summary) | `json` |
| `--log-level` | Python logging level | `WARNING` |

## Outputs

`json` mode (default):

```json
{
  "Success": true,
  "Data": {
    "findings": [
      {
        "kind": "skill_name",
        "severity": "critical",
        "target_file": "docs/old.md",
        "line": 12,
        "referenced_entity": "doc-sync",
        "recommendation": "Skill `doc-sync` not present at .claude/skills/. Update reference, restore the skill, or remove the mention."
      }
    ],
    "verdict": "CRITICAL_FAIL",
    "counts": {
      "files_scanned": 142,
      "files_skipped": 0,
      "refs_checked": 318,
      "findings_total": 1,
      "findings_suppressed": 0,
      "directive_suppressed": 0,
      "incomplete_scans": 0
    },
    "directive_suppressed": [],
    "incomplete_scans": []
  },
  "Error": null,
  "Metadata": {"Script": "scan.py", "Version": "1.0.0", "Timestamp": "..."}
}
VERDICT: CRITICAL_FAIL
```

`human` mode:

```text
orphan-ref-validator 1.0.0
  files_scanned:        142
  files_skipped:        0
  refs_checked:         318
  findings:             1
  suppressed:           0
  directive_suppressed: 0
  incomplete_scans:     0
  [critical] docs/old.md:12 skill_name `doc-sync` -- Skill `doc-sync` not present at .claude/skills/. ...
VERDICT: CRITICAL_FAIL
```

## Process

### Phase 1: Resolve Targets

- Read `--targets` if supplied, else derive default targets from `git ls-files`.
- Append `OPT_IN_ADR_TARGETS` if `--include-adrs` is set.
- Append `OPT_IN_SKILL_TARGETS` if `--include-skill-descriptions` is set.
- Expand glob patterns containing `*` or `?` against the repository root.
- Mark missing targets, outside-repo targets, and empty glob matches as incomplete scans unless `--allow-missing-targets` is set.

### Phase 2: Walk Files

- For directory targets, recurse and yield files whose suffix matches `.md`, `.json`, `.yaml`, `.yml`.
- Exclude paths whose any segment is in `EXCLUDE_DIR_NAMES` (`__pycache__`, `.git`, `node_modules`, `worktrees`, `cache`, `references`, `templates`). The first five are vendor/VCS directories; the last two are added because skill `references/` and `templates/` directories are progressive-disclosure docs that legitimately cite external entities.
- Exclude files matching the secret denylist.
- Mark unreadable files, broken symlinks, outside-repo symlinks, symlink loops, stat failures, walk failures, and files larger than 5 MB as incomplete scans.

### Phase 3: Detect References

- Apply skill, script, rule, and instruction path extractors line by line.
- Filter known-kebab tokens (model IDs, frontmatter fields, Action names, bot ids, git hooks, vocabulary terms).
- Skip script refs on example-placeholder lines, such as `Example:` and `e.g.` snippets.
- Honor the ignore directives described below.

### Ignore directives

| Directive | Scope | Where it must appear | Effect |
|---|---|---|---|
| `<!-- orphan-ref-ignore-file -->` | Whole file | Anywhere in the **first 50 lines** of the file | Skip the file entirely; emit no findings and report suppressed references under `directive_suppressed`. |
| `<!-- orphan-ref-ignore -->` | Single line | Anywhere on the same line as a reference | Skip every reference on that line and report it under `directive_suppressed`. |

Place file-scope directives below the YAML frontmatter (if any) and well within the first 50-line window. Adding a directive at line 51 or later silently fails because the scanner only reads `text.splitlines()[:50]`.

Script references on example-placeholder lines are ignored automatically. This covers lines that start with `Example:`, `e.g.`, or `For example`, plus prose examples that document an intentionally absent helper.

Use file-scope on M1-deletion specs and proposed-entity catalogs whose every reference is intentional history. Use line-scope for one-off references that document an absence (for example, "the script `scripts/validation/manifest_counts.py` was not created").

### Phase 4: Resolve and Verdict

- For each surviving reference, check the source of truth (skill set, file presence).
- Build the ADR-056 envelope with findings, counts, and verdict.
- Verdict is `CRITICAL_FAIL` if any finding has severity `critical`, else `WARN` if findings exist, else `PASS`.
- Print envelope and `VERDICT:` line. Exit 1 on CRITICAL_FAIL, 2 on usage/configuration or incomplete-scan error, 3 on external error, 4 on permission error, 0 otherwise.

## Verification

Success criteria for the skill:

- [ ] `uv run pytest .claude/skills/orphan-ref-validator/tests/ -q` reports all tests passed.
- [ ] `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --help` exits 0 with the documented argparse output.
- [ ] `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --targets missing.md` exits 2 with `VERDICT: ERROR`.
- [ ] `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py` from the repo root exits 0 with `VERDICT: PASS` on default tracked text targets.
- [ ] `.claude/commands/build.md` Mandatory Exit Gates lists orphan-ref-validator as gate 4.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/scan.py` | Main entrypoint. Argparse CLI, target resolution, walking, detection, envelope rendering, exit codes. |
| `scripts/__init__.py` | Marks `scripts/` as a Python package so tests can import `from scripts.scan import ...`. |

Invoke directly with `uv run python .claude/skills/orphan-ref-validator/scripts/scan.py [flags]`. Do not import the script from other modules; treat it as a CLI tool.

## Anti-Patterns

- Adding a new skill name to the denylist when the real fix is to register the skill or remove the reference.
- Using `<!-- orphan-ref-ignore-file -->` on an active spec to mask a real orphan; reserve the directive for historical specs and proposed-entity catalogs.
- Suppressing real script_path findings by editing the regex; instead, fix the AC text or restore the script.
- Running with `--include-skill-descriptions` at the `/build` gate before preexisting skill-description drift is cleaned; the gate becomes noisy and reviewers ignore it.

## Extension Points

- Add new entity kinds (for example, agent names) by extending `Kind`, adding a regex, and wiring `scan_file` to call a new enumerator.
- Tighten the regex for a kind by editing the corresponding `*_REF_RE` constant in `patterns.py`.
- Add per-kind exit-code escalation by branching on `result.verdict` in `main` before returning.
- Replace the markdown ignore directive with a structured config file by parsing `.orphan-ref-ignore` at the repository root.

## Behavior

### Reference detection

| Kind | Pattern | Source of truth |
|---|---|---|
| `skill_name` | `` `<kebab>` `` where `<kebab>` matches `[a-z][a-z0-9]*(?:-[a-z0-9]+)+` (at least one hyphen, no trailing hyphen); plus single-word `` `<word>` `` only when `<word>` is a curated known single-word skill name (`filters.py:KNOWN_SINGLE_WORD_SKILLS`) | `.claude/skills/<name>/SKILL.md` directories |
| `script_path` | `` `(build/scripts\|scripts/validation\|scripts\|tests)/<path>.py` `` plus skill-local `scripts/` or `tests/` `.py` paths | file existence on disk |
| `rule_path` | `.claude/rules/<name>.md` in backticks or Markdown link targets | file existence on disk |
| `instruction_path` | `.github/instructions/<name>.instructions.md` or `src/copilot-cli/instructions/<name>.instructions.md` in backticks or Markdown link targets | file existence on disk |

Common kebab-case English phrases (`well-known`, `open-source`, `step-by-step`, etc.) are filtered to reduce false positives. The filter list lives in `filters.py:is_known_kebab_word`.

Single-word (no-hyphen) skill names are detected separately: a backticked single word is treated as a skill reference only when it resolves to a live `.claude/skills/<name>/` directory (valid, no finding) or is a curated known single-word skill name in `filters.py:KNOWN_SINGLE_WORD_SKILLS` (flagged when absent). Arbitrary backticked English words are never flagged. Add a retired or renamed single-word skill to `KNOWN_SINGLE_WORD_SKILLS` so lingering references surface instead of going silent (issue #2679).

### Verdict logic

The verdict considers only active (non-suppressed) findings. A finding whose
key is in the `--baseline` is marked `suppressed` and is excluded from the
verdict calculation.

| Active findings | Verdict |
|---|---|
| Any active finding has `severity=critical` | `CRITICAL_FAIL` |
| Active findings exist, all `severity=warn` | `WARN` |
| No active findings (none, or all suppressed by baseline) | `PASS` |

### Vendored install behavior

Missing targets are incomplete scans and exit `2` by default. Truncation is also an incomplete scan: if the finding budget is exhausted, the scanner prioritizes active findings before baselined findings, adds a `scan_truncated` finding, and exits nonzero. A vendored caller that intentionally lacks repository-only paths must pass `--allow-missing-targets`; a caller that intentionally scans an empty scope must also pass `--allow-empty-scan`.

### Path safety

Target paths are resolved with `pathlib.Path.resolve()` and must lie under the repository root. Paths outside the repo, broken symlinks, symlink loops, outside-repo symlinks, walk errors, stat errors, unreadable files, and files larger than 5 MB are incomplete scans. Permission failures exit `4`; other incomplete scans exit `2` unless the reason is classified as logic or external. Files in the secret denylist (`.env*`, `secrets.*`, `*.key`, `*.pem`, `*.pfx`, `*.p12`, `id_rsa(.pub)?`, `id_ed25519(.pub)?`, `id_ecdsa(.pub)?`, `id_dsa(.pub)?`, `.netrc`, `.npmrc`, `.pypirc`, `credentials`) are excluded.

## Failure modes

| Mode | Behavior |
|---|---|
| Missing target path | Exit 2 unless `--allow-missing-targets` is set |
| Zero files scanned | Exit 2 unless `--allow-empty-scan` is set |
| Target file unreadable (permissions) | Exit 4 with incomplete-scan count |
| Manifest with malformed JSON | scanned as text; skill/script references still extracted |
| Broken symlink | Incomplete scan; logged as `WARNING` |
| Symlink loop | Incomplete scan; logged as `WARNING` |
| Symlink directory pointing outside repo | Incomplete scan; logged as `WARNING` (CWE-22 / CWE-59) |
| Symlink file pointing outside repo | Incomplete scan; logged as `WARNING` |
| Oversized files (>5 MB) | Incomplete scan; logged as `WARNING` |
| UTF-8, UTF-16, or UTF-32 file with BOM | Decoded and scanned |
| Unsupported or malformed encoding | Incomplete scan; no replacement decode |

## When the /build gate fails

If `/build` exits with `VERDICT: CRITICAL_FAIL` from this skill, the recovery is:

1. Re-run with the human formatter to get a grep-able list of `path:line` findings:

   ```bash
   uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --output human
   ```

2. For each finding, choose one of three resolutions named in the recommendation string:

   | Finding kind | Three options |
   |---|---|
   | `skill_name` | restore the skill, update the reference, or remove the mention |
   | `script_path` | restore the script, update the reference, or remove the mention |

3. If the reference is intentional historical or proposed-entity documentation, add a line-scope `<!-- orphan-ref-ignore -->` (single line) or a file-scope `<!-- orphan-ref-ignore-file -->` (whole file). See "Ignore directives" above for placement rules.

4. Re-run the skill and confirm `VERDICT: PASS`.

## Investigation workflow

To find latent drift in surfaces that are opt-in by default:

```bash
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
    --include-adrs \
    --include-skill-descriptions \
    --output human
```

This adds `.agents/architecture/`, `docs/`, and every `.claude/skills/*/SKILL.md` to the scan. The output is intentionally noisy on first run because preexisting drift surfaces; treat it as a triage list, not a `/build` gate.

## Examples

```bash
# Default scan from repo root
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py

# Scan only one file
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
    --targets docs/skill-reference.md

# Human summary
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --output human
```

## Tests

```bash
uv run pytest .claude/skills/orphan-ref-validator/tests/ -q
```

Coverage target is 80 percent line coverage on `scan.py`. Cases cover positive and negative detection for each kind, the ADR-056 envelope shape, vendored-install scenarios, and edge cases (empty file, mixed living-and-dead refs, large files, secret files).

## Wiring

### `/build` Mandatory Exit Gate

`.claude/commands/build.md` invokes the skill. Exit `1` blocks the build phase.

### PR exit gate: scope to changed files

A default repo-wide scan (no `--targets`) fails on pre-existing orphan refs that
predate the gate, so it is not a usable PR gate on a repo that already carries
debt. Two patterns avoid that:

1. **Scope to the changed files** so the gate judges only what the PR touches:

   ```bash
   uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
       --targets $(git diff --name-only origin/main...HEAD)
   ```

   A PR that introduces no new orphan ref exits `0`; a PR that adds one exits `1`.
   This is the recommended PR exit-gate form.

2. **Baseline the known debt** so a repo-wide scan suppresses pre-existing
   findings and fails only on new ones. See "Generating a baseline" below.

### Generating a baseline

Capture the current repo-wide findings once, commit the baseline, and the gate
then fails only on findings introduced after that snapshot:

```bash
# Save the current full scan as the baseline (JSON envelope form).
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
    --include-adrs --include-skill-descriptions \
    --output json > orphan-ref-baseline.json

# Later runs suppress the baselined findings; new ones still fail.
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
    --include-adrs --include-skill-descriptions \
    --baseline orphan-ref-baseline.json
```

The baseline file accepts three shapes: a saved JSON envelope (`Data.findings`,
as produced above), a JSON list of key strings, or a plain-text file with one
`target_file:line:kind:referenced_entity` key per line (`#` comments allowed).
Keys are positional: editing a file shifts line numbers, so regenerate the
baseline after touching a baselined file, or prefer the changed-files form for
PR gating. Treat the baseline as debt to pay down, not a permanent allowlist.

### Pre-push hook (optional)

Repos that want a tighter feedback loop can add a pre-push hook that runs the skill against the push changeset (the commits being pushed, not the index state). Use `git diff --name-only @{push}..HEAD` (or the equivalent post-receive computation) to scope `--targets` to changed files. The skill is read-only and exits `1` on critical findings, which the hook can use to block the push.

## References

- REQ-009, DESIGN-009, TASK-009 (specs in `.agents/specs/`)
- ADR-035 (exit codes)
- ADR-042 (Python first)
- ADR-056 (skill output envelope)
- `.claude/rules/canonical-source-mirror.md` (citation policy)
- Companion validators: `build/scripts/validate_plugin_manifests.py`

<!-- vendor-portability: declared. This skill already degrades gracefully: it states that when a target path such as .agents/ is absent it logs INFO and continues. The .agents/specs/ and .agents/architecture/ defaults are scan targets, not preconditions; a vendored install scans only the paths that exist. Issue #2050. -->
