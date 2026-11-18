# sync

Scans your REQ, DESIGN, and TASK specs for references to code that no longer exists, then reports each one so you can triage it. It reports drift and never edits a spec.

> [!NOTE]
> This skill is a drift detector for the `rjmurillo/ai-agents` repository. It runs [`scripts/sync/detect_spec_drift.py`](../../scripts/sync/detect_spec_drift.py) over that repository's spec tiers. The script does not ship in a plugin root, so the skill is for contributors working in a checkout of the repository.

## When to use it

- You hand-edited code (a refactor, hotfix, or rename) and want to know which specs now point at missing paths.
- You say `detect spec drift`, `sync the specs`, or `did my refactor break a spec`.
- You want to find drift while you still remember why you changed the code, not later at `/review`.

## When not to use it

- You want to write a spec: use [`spec`](spec.md) instead.
- You want specs rewritten for you: this skill does not do that. It reports and never edits.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:sync
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/sync`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /sync skill to ...`.

To scan one tier, pass its directory:

```text
/sync .project-toolkit/specs/design
```

You see a verdict line and one line per finding, in the form `spec_file:line -> path absent on disk`.

## What you get

- The detector's `VERDICT` line: `PASS` or `DRIFT`.
- A list of findings, each as `spec_file:line -> path`.
- A triage decision per finding, which the skill asks you to confirm with the author of the change.

| Exit code | Meaning |
| --- | --- |
| `0` | No drift |
| `1` | Drift found |
| `2` | Configuration error: unsafe target, unreadable spec, or missing custom target |

## Advanced use

The detector scans `.project-toolkit/specs/requirements`, `.project-toolkit/specs/design`, and `.project-toolkit/specs/tasks`. It looks for backticked references to code and artifact paths under its known roots (scripts, build, skills, commands, templates, tests, and source). It resolves each reference against the working tree. A path absent on disk is drift.

Run it directly from the root of a checkout of this repository:

```bash
uv run python scripts/sync/detect_spec_drift.py --output-format human
uv run python scripts/sync/detect_spec_drift.py --target .project-toolkit/specs/design --output-format human
```

| Flag | Effect |
| --- | --- |
| `--repo-root` | Repository root. Defaults to walking up from the current directory. |
| `--target` | Spec tier directory to scan. Repeatable. Defaults to REQ, DESIGN, and TASK. |
| `--output-format` | `json` (ADR-056 envelope) or `human`. |

Unsafe `--target` values (absolute paths, `..`, or symlink escapes) exit `2`. Unsafe references inside a spec are reported as drift.

### Triage

For each finding, pick one case:

| Case | Action |
| --- | --- |
| Code moved | Update the spec reference to the new path. |
| Code deleted | Update the spec to reflect the removal, or restore the code if the removal was unintended. |
| Intentional forward reference | Add a trailing `<!-- sync-drift-ignore -->` so the detector skips the line. |
| Unsafe reference (`..`, absolute path, symlink escape) | Treat as drift and change it to a repo-contained path. |

Confirm each case with the author of the change before you touch the spec. Record the rationale in the PR description.

The skill does not auto-apply edits. Handing findings to [`spec-generator`](spec-generator.md) to draft patches, and writing a sync log, are named in the source as planned follow-ups and are not wired yet.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec`](spec.md): writes the specs this skill checks.
- [`spec-generator`](spec-generator.md): the planned source of spec patches.
- [`review`](review.md): where unnoticed drift would otherwise surface.
- Source: [`SKILL.md`](../../src/claude/skills/sync/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
