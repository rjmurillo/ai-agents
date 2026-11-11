# Memory with Serena and learning from sessions

## Goal

By the end of this page you will have done four things. You will search project memory and read one entry by name. You will see the Stop-hook nudge fire on a sample transcript. You will know when to use `reflect` and when to use `retrospective`.

You will check each step with output you can compare to this page.

## Before you start

- A clean checkout of `rjmurillo/ai-agents` on `main`. See [installation](../installation.md) if you do not have one.
- Python 3 on your path. The commands below use `python3` and `git`.
- Serena active in your agent session is optional for steps 1 and 2. It is needed to write memory in the later sections.

## How memory works

Serena is the only memory backend ([ADR-106](../../.project-toolkit/architecture/ADR-106-serena-only-memory-architecture.md)). A memory is a plain Markdown file under `.serena/memories/`. It travels with the repository, so it stays readable when the MCP server is down. The second memory server was removed in [#5575](https://github.com/rjmurillo/ai-agents/pull/5575). The decision record landed in [#5656](https://github.com/rjmurillo/ai-agents/pull/5656).

The rule for reading is: search first, then read by name. Do not list every memory. A full `list_memories` call costs thousands of tokens (see `.serena/memories/README.md`).

| Skill | Use it to |
|---|---|
| `memory-search` | Find memories by keyword. |
| `memory-gate` | Check memory before you change something that already exists. |
| `memory` | Route to the right memory skill when you are not sure which. |
| `memory-consolidate` | Merge duplicates and tidy the index (see [#4832](https://github.com/rjmurillo/ai-agents/pull/4832)). |
| `memory-reflexion` | Extract an episode from an existing session log. New session logs are no longer created, so you rarely need it. |

## Steps

### 1. Search memory

Run the search script from the repository root.

```bash
python3 .claude/skills/memory/scripts/search_memory.py "git hooks" --max-results 3 --format table
```

### 2. Read one entry by name

The search result names each memory. Read the first one. With Serena active, your agent calls `read_memory("git/git-hooks-001-pre-commit-branch-validation")`. Without Serena, read the same file.

```bash
head -4 .serena/memories/git/git-hooks-001-pre-commit-branch-validation.md
```

### 3. Use the gate before you change something

Before you change code, a rule, or a protocol, search memory for why it exists. The `memory-gate` skill makes this step required. Say `memory-first gate` to your agent, or run the search yourself:

```bash
python3 .claude/skills/memory/scripts/search_memory.py "pre-commit hook" --max-results 3 --format table
```

Write what you found into your decision notes or PR description. The gate wants proof that the search happened before the change.

### 4. See the Stop-hook nudge fire

A Stop hook scans your session transcript when a turn ends. It looks for corrections ("no, wrong branch") and praise or preferences ("perfect", "prefer short names"). When it finds at least one correction or two praise or preference signals, it prints one advisory line. It never blocks, never writes memory, and always exits 0 (see [#6095](https://github.com/rjmurillo/ai-agents/pull/6095)).

Build a sample transcript and a state directory outside the repository:

```bash
WORK=$(mktemp -d)
printf '%s\n' \
  '{"type":"user","origin":{"kind":"human"},"message":{"content":"no, wrong branch"}}' \
  '{"type":"user","origin":{"kind":"human"},"message":{"content":"perfect"}}' \
  '{"type":"user","origin":{"kind":"human"},"message":{"content":"exactly, prefer short names"}}' \
  > "$WORK/session.jsonl"
PAYLOAD=$(printf '{"session_id":"demo-1","transcript_path":"%s/session.jsonl","cwd":"."}' "$WORK")
```

Run the hook:

```bash
echo "$PAYLOAD" | XDG_STATE_HOME="$WORK" python3 -u .claude/hooks/Stop/invoke_reflect_nudge.py
```

Run it a second time with the same command. The hook nudges once per session and signal set, so the second run is silent on stdout.

The friction branch is separate. It scores permission denials, Stop-hook feedback, and error streaks. At a score of 10 it adds a line that points to `/retrospective` instead ([#7073](https://github.com/rjmurillo/ai-agents/pull/7073)). Plugin users get the same hook as an advisory Stop hook ([#7092](https://github.com/rjmurillo/ai-agents/pull/7092)).

To turn the nudge off, set `AI_AGENTS_RETRO_NUDGE_THRESHOLD=off` (or `0`).

### 5. Pick `reflect` or `retrospective`

| Situation | Use |
|---|---|
| You corrected the agent, or praised an output. | `reflect` |
| You found an edge case in one skill. | `reflect` |
| `main` went red, or a merge was reverted. | `retrospective` |
| You want Five Whys on a failed task. | `retrospective` |
| The friction nudge fired. | `retrospective` |
| You want a Markdown artifact under `.project-toolkit/retrospective/`. | `retrospective` |

`reflect` is small. It scans the conversation, shows you HIGH, MED, and LOW findings, and writes to Serena only after you approve. It stores them in `.serena/memories/<skill>-observations.md`.

`retrospective` is large. It gathers evidence from git, runs root-cause analysis, scores each learning for atomicity, and writes one artifact. Learnings at or above 70 percent atomicity go to Serena memory.

To see the retrospective script options, run:

```bash
python3 .claude/skills/retrospective/scripts/run_retrospective.py --help
```

Writes to Serena belong in the checkout where Serena started. A linked worktree must not call `write_memory`. See the `reflect` skill for the rule.

## Check your result

Compare what you saw with this list.

1. Step 1 printed a table headed `Name Source Score Tokens Preview`. It listed three `git/git-hooks-...` entries, each with source `Serena`. The last line was `Token budget: 2325 tokens (cumulative for 3 results)`.
2. Step 2 printed a heading, `# Skill: Git-001 Pre-Commit Branch Validation`, followed by a blank line, `**Atomicity Score**: 90%` and the source line.
3. Step 4 printed this on stdout the first time:

   ```text
   {"systemMessage": "reflect-trigger: this session holds 1 correction and 2 praise or preference signal(s). You can run /reflect to review and approve what to keep."}
   ```

   The second run printed nothing on stdout. Stderr said `already nudged`.

The token count in step 1 and the scores can change as memories are added. The structure should not.

## If it fails

| Symptom | Cause | Fix |
|---|---|---|
| `search_memory.py` exits 1. | The query is empty or over 500 characters. | Shorten the query. |
| `search_memory.py` exits 2. | A path argument contains `..`, or `AI_AGENTS_REPO_ROOT` is not a directory. | Drop the path argument or fix the variable. |
| The hook prints nothing on the first run. | `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is `0` or `off`, or the state directory sits inside a git repository. | Unset the variable. Point `XDG_STATE_HOME` at a directory outside any repository. |
| Stderr says `HOME unset, state root refused`. | The hook refuses to guess a state directory. | Set `HOME` or `XDG_STATE_HOME`. |
| The hook finds too few signals. | One correction or two praise or preference turns are the minimum. Only human-typed turns count. | Add more turns with `"origin":{"kind":"human"}`. |

## Reference sources

- [ADR-106](../../.project-toolkit/architecture/ADR-106-serena-only-memory-architecture.md): the Serena-only decision.
- `.serena/memories/README.md`: directory layout, index format, size limits.
- `src/claude/skills/memory-search/SKILL.md`, `memory-gate/SKILL.md`, `memory-consolidate/SKILL.md`: the memory skills.
- `src/claude/skills/reflect/SKILL.md` and `src/claude/skills/retrospective/SKILL.md`: the two learning skills.
- `.claude/hooks/Stop/invoke_reflect_nudge.py`: the nudge, with its exit-code contract and patterns.

## Next

Return to the [training index](README.md).
