# memory-reflexion

Extracts an episode record from a completed session log. Later sessions can replay what was tried and what it cost.

## When to use it

- A session reached a terminal outcome and you want a durable record of it.
- You need to refresh an episode record that already exists.
- Trigger phrases: `extract episode from session`, `record what happened this session`, `re-extract this episode`.

## When not to use it

- You want a Tier 1 lookup: use [`memory-search`](memory-search.md).
- You want to add citations: use [`memory-enhancement`](memory-enhancement.md).

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:memory-reflexion`. The [`memory`](memory.md) router loads it when your request matches. To ask for it by name, say:

```text
Use the memory-reflexion skill to extract an episode from the finished session log at .project-toolkit/sessions/2026-11-01-session-04.json.
```

The skill runs the extractor, then you confirm the episode file exists and its outcome matches how the session ended.

## What you get

An episode JSON record in the repository episode store. The extractor reports the episode ID and outcome. The new file shows up in `git status`, because episodes are committed. The schema comes from ADR-038 and is described in [`references/reflexion-memory.md`](../../src/claude/skills/memory-reflexion/references/reflexion-memory.md).

Only extract from completed sessions. A partial session yields an incomplete episode, which is a falsified record that outlives the session. An episode that records `success` for an abandoned session is worse than none. To fix a wrong record, fix the session log and re-extract. Do not hand-edit an episode.

`memory-search` is the reader of episodes today. The source says whether episodes earn their keep is an open question that ADR-089 declined to settle.

## Advanced use

Run the extractor from the root of a checkout of this repository:

```bash
uv run python .claude/skills/memory/scripts/extract_session_episode.py .project-toolkit/sessions/2026-11-01-session-04.json --preserve
```

| Flag | Meaning |
| --- | --- |
| `session_log_path` | Path to the session log. Required. |
| `--output-path` | Output directory for episode JSON. |
| `--force` | Overwrite an existing episode file. |
| `--preserve` | Merge a fresh extraction over the existing record without dropping richer existing data. |
| `--validate` | Validate an episode JSON file, or every `*.json` under a directory, instead of extracting. Exit 2 on a duplicate, missing, or non-contiguous event id, or a backwards commit edge. |
| `--fix` | With `--validate`, repair backwards commit order in place. |
| `--dry-run` | Run extraction and every refusal check, print what would be written, and write nothing. Not valid with `--validate`. |
| `--pending-stage` | Add 1 to the staged files count for the episode file about to be staged (pre-commit context). |

`--force` and `--preserve` are mutually exclusive. If an episode file already exists and you pass neither, choose one deliberately.

| Symptom | Cause | Recovery |
| --- | --- | --- |
| Episode not found | Wrong session log path, or session incomplete | Check the path and the session's terminal outcome. |
| Episode file already exists | A prior extraction wrote it | Use `--force` to replace or `--preserve` to merge. |
| Outcome reads wrong | The session log's terminal state is ambiguous | Fix the session log first. |

The write path is local-only. It needs no network store. The earlier causal-graph step that folded episodes into a Tier 3 layer was removed by ADR-089.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`memory`](memory.md): the router that sends session-recording requests here, and owner of the script.
- [`memory-search`](memory-search.md): reads episodes through Tier 1 search.
- [`memory-enhancement`](memory-enhancement.md): citations and confidence scores.
- Source: [`SKILL.md`](../../src/claude/skills/memory-reflexion/SKILL.md)
- Reference: [`reflexion-memory.md`](../../src/claude/skills/memory-reflexion/references/reflexion-memory.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
