# orphan-ref-validator

Scans specs, ADRs, eval fixtures, plugin manifests, and rules for references to skills, scripts, rules, and instruction files that no longer exist in the working tree. It blocks stale references before you commit, instead of after a PR review.

## When to use it

- You removed or renamed a skill or script and want to find every reference left behind.
- You want the `/build` exit gate to fail on orphan references.
- Trigger phrases: `scan for orphan refs`, `validate orphan references`, `check skill catalog drift`.

## When not to use it

- You want to verify that doc claims match code behavior: use [`doc-accuracy`](doc-accuracy.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:orphan-ref-validator`. The [`test`](test.md) lifecycle invokes it, and the agent loads it when your request matches. To ask for it by name, say:

```text
Use the orphan-ref-validator skill to scan the files changed on this branch for references to skills or scripts that do not exist.
```

The skill runs `scan.py` and reports findings with file, line, kind, and a recommendation. It ends with a `VERDICT:` line.

## What you get

| Finding kind | What it means |
| --- | --- |
| `skill_name` | A skill name with no skill directory |
| `script_path` | A script path that is not on disk |
| `rule_path` / `instruction_path` | A rule or instruction file path that is not on disk |
| `retired_path` | A citation of a retired slash-command directory in a live guidance document |

Verdicts and exit codes:

| Verdict | Exit | Meaning |
| --- | --- | --- |
| `PASS` | `0` | No active findings |
| `WARN` | `0` | Active findings, none critical |
| `CRITICAL_FAIL` | `1` | At least one critical finding |
| `ERROR` | `2` | Usage, configuration, or incomplete scan |
| (none) | `3` | External failure |
| (none) | `4` | Permission failure |

The default output is a JSON envelope with `findings`, `verdict`, and `counts` (`files_scanned`, `refs_checked`, `findings_total`, and others). Use `--output human` for a compact summary.

## Advanced use

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --help
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --output human
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --targets docs/guide.md --output human
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --include-adrs --include-skill-descriptions --baseline orphan-ref-baseline.json
```

Flags:

| Flag | Purpose |
| --- | --- |
| `--targets` | Files or directories to scan (default: tracked docs, specs, rules, instructions, and tests) |
| `--include-adrs` | Add architecture records and `docs/` (opt-in, noisy) |
| `--include-skill-descriptions` | Add every skill's `SKILL.md` (opt-in) |
| `--allow-missing-targets` | Treat missing targets as optional, for partial vendored installs |
| `--allow-empty-scan` | Permit `PASS` after scanning zero files |
| `--baseline` | File of known finding keys; matching findings are suppressed |
| `--repo-root` | Repository root (default: found from the current directory) |
| `--output` | `json` or `human` |
| `--log-level` | Python logging level |

**Scope a PR gate to changed files.** A repository-wide scan fails on old debt. Pass only the files your branch changed. This form keeps paths with spaces intact:

```bash
git diff -z --name-only --diff-filter=d origin/main...HEAD | xargs -0 -r uv run python .claude/skills/orphan-ref-validator/scripts/scan.py --targets
```

A path that starts with `-` is still read as an option, so rename such a file before you scan. A changed file that already had orphans still fails the scan, even on lines your PR did not touch. Record that old debt with `--baseline`, described next, so only new orphans fail.

**Baseline known debt.** Save a full scan as JSON and pass it with `--baseline`. Baseline keys are positional (`target_file:line:kind:referenced_entity`), so regenerate the baseline after you edit a baselined file. Treat it as debt to pay down.

**Ignore directives.** `<!-- orphan-ref-ignore -->` on a line skips references on that line. `<!-- orphan-ref-ignore-file -->` in the first 50 lines skips the file. Use the file form only for historical specs and proposed-entity catalogs, never to hide a real orphan on an active spec. Suppressed references appear under `directive_suppressed`.

**Check a finding before you fix it.** The scanner has produced many false positives in past runs. Open the cited line and decide whether the reference was meant to resolve. For a real finding, restore the entity from git history, update the reference, or remove the mention. Restore never means writing a new entity so the reference resolves.

Missing targets, unreadable files, broken or outside-repo symlinks, symlink loops, and files over 5 MB all count as incomplete scans. The scanner excludes files that look like secrets (such as `.env*` and `*.pem`).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`test`](test.md): invokes this skill as part of its gates.
- [`build`](build.md): lists this skill as a Mandatory Exit Gate.
- [`doc-accuracy`](doc-accuracy.md): checks doc claims against code.
- Source: [`SKILL.md`](../../src/claude/skills/orphan-ref-validator/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
