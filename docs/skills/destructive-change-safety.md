# destructive-change-safety

Proves the blast radius and the recovery path before a change deletes, overwrites, drops, or revokes state. It blocks the change when scope is unknown, the count is wrong, or no rollback exists.

## When to use it

- A change can reach code that deletes rows, files, or resources, overwrites canonical state, drops or truncates, force-pushes, or revokes credentials.
- You want a rollback plan for an irreversible migration.
- Trigger phrases: `is this delete safe`, `blast radius`, `check this destructive change`, `rollback plan for this change`.

## When not to use it

- The change is read-only: the scan returns `skip` and the skill ends.
- You want a security review: use [`security-scan`](security-scan.md).

This skill does not replace deployment tooling, migration tooling, or backups.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:destructive-change-safety is it safe to delete stale worktrees in scripts/cleanup.py?
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/destructive-change-safety`.

The skill scans the package for destructive sinks, previews the scope without mutating anything, asks for a rollback contract, then runs a gate that returns `PASS`, `SKIP`, or `BLOCK`.

## What you get

The gate returns one JSON verdict:

| Verdict | Exit | Meaning |
| --- | --- | --- |
| `PASS` | 0 | Every sink is traced, scope is measured and as expected, rollback is stated, and checks are green. Execution may proceed. |
| `SKIP` | 0 | No sink was declared, and a scan report with `"decision": "skip"` backs it. |
| `BLOCK` | 1 | `reasons` lists each failure. Fix the evidence or stop. |

The gate blocks on cardinality outside `expected`, a missing or failed preflight, no rollback, an irreversible step without human approval, a failed check, or a missing scan report. It has no override. Quote the verdict in the PR body.

## Advanced use

The work runs in four phases, all through one script. Every subcommand is read-only and prints one JSON object. Run them from the root of a checkout of this repository:

```bash
uv run python .claude/skills/destructive-change-safety/scripts/destructive_gate.py scan scripts --base . --changed delete_user
```

| Subcommand | Purpose | Exit codes |
| --- | --- | --- |
| `scan` | Sinks, caller chains, flags, forward trace. Takes `paths`, `--base`, and `--changed`. | 0 ran, 1 unparsed or unscanned file, 2 bad path or no scannable file |
| `preview-files` | Files a glob would touch. Takes `--root` and `--pattern`. | 0 counted, 1 refused |
| `preview-sql` | Rows a SQLite DELETE or UPDATE would change. Takes `--database` and `--statement`. | 0 counted, 1 refused |
| `gate` | Fail-closed verdict. Takes `--evidence` and `--scan`. | 0 PASS or SKIP, 1 BLOCK, 2 bad input |

**Phase 1, trace sinks.** Scan the whole package, not only the edited file, and pass each edited function to `--changed`. Read these fields: `chains` (call paths to the sink), `flags` (CLI flags along those chains, where a new flag is a new route to the sink), `reached_from_changed` (empty means no path found, not that none exists), and `callers_unknown` (true means widen the scan or read the callers by hand). Decision `unknown` exits 1 when a file did not parse or a file the scan cannot read went unscanned, such as PowerShell, JavaScript, C#, Go, YAML, Makefile, Dockerfile, or any shebang file. Read those by hand.

**Phase 2, measure without mutating.** Use `preview-sql` for SQLite and `preview-files` for globs. `preview-sql` runs the statement on an in-memory copy: `count` is rows hit and `total_changes` includes cascades and triggers. For other engines, use the system's own dry run or `SELECT COUNT`, and record the real output. If no safe preview exists, treat scope as unknown. Do not estimate.

**Phase 3, state the rollback.** Choose `backup`, `snapshot`, `version`, or `irreversible`.

- `backup`: give `backup_path` and `source_path`. The gate hashes both and requires a match.
- `snapshot`: give `snapshot_path` and `snapshot_target`. The path is a manifest file or a directory holding `snapshot.json` with `format` (`destructive-change-snapshot`), `version` (`1`), `ref`, `target`, `payload` (a relative path), and `sha256` of the payload. The gate checks every field.
- `version`: `ref` must be a 40-hex commit id that `git cat-file` finds. A pass means the commit exists. You still own the claim that it restores the data.
- `irreversible`: record human approval. An agent never invents a rollback or approves its own irreversible step.

**Phase 4, gate.** Run the tests that cover the sink and record each command and exit code from this run. Write an evidence file with `sinks`, `preflight`, `expected` (an exact count, or an object with a `max` key), `rollback`, `approval`, and `checks`, then run `gate` with `--evidence` and `--scan`.

[`autoplan`](autoplan.md) routes destructive-change and blast-radius requests here. The skill depends on the technical-review protocol of [`review`](review.md) for reading callers outside the scanned set.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`security-scan`](security-scan.md): the security review this skill does not replace.
- [`review`](review.md): its technical-review protocol covers callers outside the scan.
- [`autoplan`](autoplan.md): routes blast-radius requests here.
- Source: [`SKILL.md`](../../src/claude/skills/destructive-change-safety/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
