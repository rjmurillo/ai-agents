# Session mining

SkillOpt needs eval tasks. Real tasks come from your own session history.
`mine_sessions.py` turns local transcripts into a per-skill usage and
weak-correction map, and pulls the prompts that triggered a skill as
candidate eval tasks.

Commands below run from the skill directory. On Windows use `py -3` and a
backslash path, for example:

```powershell
py -3 scripts\mine_sessions.py sources
```

## Supported sources

| Source | Default path | Notes |
|--------|--------------|-------|
| Claude Code transcripts | `~/.claude/projects/**/*.jsonl` | Override with `--root PATH` (repeatable). Skip with `--no-claude`. |
| GitHub Copilot CLI session store | `~/.copilot/session-store.db` | Opened read-only. Override with `--copilot PATH`. Skip with `--no-copilot`. |
| `session-patterns/1` handoff | none | `--patterns FILE`. Replaces transcript reads. |

`~` is the user's home directory on Linux, macOS, and Windows. Other
harnesses, including Codex CLI and Gemini CLI, are not read directly. Export
their sessions as a `session-patterns/1` file instead.

Check what this machine can read:

```bash
python3 scripts/mine_sessions.py sources
```

A missing or unreadable source is skipped, never fatal. With no available
source and no `--patterns`, `rank`, `tasks`, and `collect` print a note to
stderr and return an empty result with exit 0. Each invocation earns at most
one correction, so corrections never exceed invocations. Each Claude transcript file and each Copilot session is one session; a
correction in one session never counts against a skill invoked in another.

## Handoff from a companion skill

A session-recall style skill can emit this local-only shape:

```json
{
  "schema": "session-patterns/1",
  "producer": "session-recall",
  "patterns": [
    {
      "id": "stable-pattern-id",
      "skill": "build",
      "sessions": ["session-a", "session-b"],
      "invocations": 3,
      "corrections": 2,
      "prompts": ["first real prompt", "second real prompt"]
    }
  ]
}
```

```bash
python3 scripts/mine_sessions.py rank --patterns patterns.json
python3 scripts/mine_sessions.py tasks --patterns patterns.json --skill build
```

The miner validates the schema: unique ids, nonempty sessions and prompts, a
positive integer invocation count, and corrections no larger than
invocations. A bad handoff exits 2.

## One machine

```bash
python3 scripts/mine_sessions.py rank --top 15
python3 scripts/mine_sessions.py tasks --skill build --limit 20
```

## Several machines

Pool aggregate counts, not transcripts. On each machine, write a baseline to a
directory you choose, outside the installed skill:

```bash
python3 scripts/mine_sessions.py collect --host laptop --out ~/skillopt-baselines/laptop.json
```

Then merge every baseline in that directory:

```bash
python3 scripts/mine_sessions.py merge --baselines-dir ~/skillopt-baselines --top 20
```

Move baseline files between machines however you like. An unreadable,
malformed, or inconsistent baseline file (a skill with more corrections than
invocations) exits 2 and names the file.

## Privacy

- `collect` writes only aggregate counts per skill (invocations and
  corrections), a skill count, and a host label. The label defaults to the
  hostname; pass `--host` to choose another. No prompt text, message content,
  or file paths.
- `tasks` prints real prompt text. Keep that output local. Do not commit it or
  send it anywhere the user has not named.

## The honest caveat

The correction rate is a weak ranking signal, not a label. The cues favor
precision; broad cues such as a bare "no" scored every skill near 1.0. Use the
ranking only to nominate a skill. Before funding rollouts, confirm the defect
exists in the target text and recurs in at least two distinct sessions. Then
derive the real pass or fail labels by judging each exchange against a frozen
verifier, and feed those to `skillopt.py`.
