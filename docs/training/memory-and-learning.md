# Search project memory and turn sessions into lessons

## Goal

By the end of this page you will have searched project memory, read one entry by name, and seen the Stop-hook nudge fire on a sample transcript. You will also know when to use `reflect` and when to use `retrospective`. This page is for everyone who runs agents in this repository.

You will know it worked when your output matches the blocks under "Check your result".

## Before you start

- A clean checkout of `rjmurillo/ai-agents` on `main`. See [installation](../installation.md) if you do not have one.
- `uv` and `git` on your path. Every repo command below uses `uv run python`.
- Serena running in your agent session is optional for steps 1 to 4. You need it only to write memory.

Serena is the only memory backend ([ADR-106](../../.project-toolkit/architecture/ADR-106-serena-only-memory-architecture.md)). A memory is a plain Markdown file under `.serena/memories/`. It travels with the repository, so it stays readable when the MCP server is down. The second memory server was removed in [#5575](https://github.com/rjmurillo/ai-agents/pull/5575). The decision record landed in [#5656](https://github.com/rjmurillo/ai-agents/pull/5656).

The reading rule is: search first, then read by name. Do not list every memory. One full `list_memories` call costs thousands of tokens, as the [memory README](../../.serena/memories/README.md) measures.

These skills do the work:

| Skill | Use it to |
|---|---|
| `memory-search` | Find memories by keyword. |
| `memory-gate` | Check memory before you change something that already exists. |
| `memory` | Route to the right memory skill when you are not sure which. |
| `memory-consolidate` | Merge duplicates and tidy the index ([#4832](https://github.com/rjmurillo/ai-agents/pull/4832)). |
| `memory-reflexion` | Extract an episode from an existing session log. New session logs are no longer created, so you rarely need it. |

## Steps

1. Search memory. Run the search script from the repository root.

   ```bash
   uv run python .claude/skills/memory/scripts/search_memory.py "git hooks" --max-results 3 --format table
   ```

   Output:

   ```text
   Name                                     Source     Score    Tokens     Preview
   ----------------------------------------------------------------------------------------------------
   git/git-hooks-001-pre-commit-branch-validation Serena     1.0      748        # Skill: Git-001 Pre-Commit Branch Validation **Atomicity...
   git/git-hooks-002-branch-recovery-procedure Serena     1.0      797        # Skill-Git-002: Branch Recovery from Main Commit **State...
   git/git-hooks-004-branch-name-validation Serena     1.0      780        # Skill-Git-Hooks-004: Branch Name Validation Pre-Commit ...

   Token budget: 2325 tokens (cumulative for 3 results)
   ```

2. Read one entry by name. With Serena active, your agent calls `read_memory("git/git-hooks-001-pre-commit-branch-validation")`. Without Serena, read the same file.

   ```bash
   head -4 .serena/memories/git/git-hooks-001-pre-commit-branch-validation.md
   ```

   Output:

   ```text
   # Skill: Git-001 Pre-Commit Branch Validation

   **Atomicity Score**: 90%
   **Source**: Session 04 retrospective - User correction
   ```

3. Search before you change something. The `memory-gate` skill makes this step required: before you change code, a rule, or a protocol, search memory for why it exists. Say `memory-first gate` to your agent, or run the search yourself.

   ```bash
   uv run python .claude/skills/memory/scripts/search_memory.py "pre-commit hook" --max-results 3 --format table
   ```

   Write what you found into your decision notes or PR description. The gate wants proof that the search came before the change. The hits and scores change as memories are added. The columns do not.

4. See the Stop-hook nudge fire. A Stop hook scans your session transcript when a turn ends. It looks for corrections ("no, wrong branch") and for praise or stated preferences ("perfect", "prefer short names"). It nudges when it finds one correction or two praise or preference signals. It never blocks, never writes memory, and always exits 0 ([#6095](https://github.com/rjmurillo/ai-agents/pull/6095)).

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
   echo "$PAYLOAD" | XDG_STATE_HOME="$WORK" uv run python -u .claude/hooks/Stop/invoke_reflect_nudge.py
   ```

   Output (the first line is stdout, the second is stderr):

   ```text
   {"systemMessage": "reflect-trigger: this session holds 1 correction and 2 praise or preference signal(s). You can run /reflect to review and approve what to keep."}
   reflect-trigger: 3 lines scanned, 3 user records, 3 human turns, 1 HIGH, 2 MED, 0 skipped lines, 0 records over event cap (nudged, friction score 0 tier 0)
   ```

   Run the same command again. The hook nudges once per session and signal set, so stdout is empty and stderr ends with `(already nudged, friction score 0 tier 0)`.

   A second branch watches for friction: permission denials, Stop-hook feedback, and error streaks. At a score of 10 it adds a line that points to `/retrospective` ([#7073](https://github.com/rjmurillo/ai-agents/pull/7073)). Plugin users get the same hook as an advisory Stop hook ([#7092](https://github.com/rjmurillo/ai-agents/pull/7092)). To turn the nudge off, set `AI_AGENTS_RETRO_NUDGE_THRESHOLD=off` (or `0`).

5. Pick `reflect` or `retrospective`.

   | Situation | Use |
   |---|---|
   | You corrected the agent, or praised an output. | `reflect` |
   | You found an edge case in one skill. | `reflect` |
   | `main` went red, or a merge was reverted. | `retrospective` |
   | You want Five Whys on a failed task. | `retrospective` |
   | The friction nudge fired. | `retrospective` |
   | You want a Markdown artifact under `.project-toolkit/retrospective/`. | `retrospective` |

   `reflect` is small. It scans the conversation and shows you HIGH, MED, and LOW findings. It writes to Serena only after you approve, into `.serena/memories/<skill>-observations.md`.

   `retrospective` is large. It gathers evidence from git, runs root-cause analysis, and scores each learning for atomicity. It writes one artifact. Learnings at or above 70 percent atomicity go to Serena memory.

   See the retrospective options:

   ```bash
   uv run python .claude/skills/retrospective/scripts/run_retrospective.py --help
   ```

   Output (first lines):

   ```text
   usage: run_retrospective.py [-h] [--scope SCOPE] [--project-dir PROJECT_DIR]
                               [--since SINCE] [--learning LEARNINGS]
                               [--fill FILL] [--output OUTPUT]
   ```

   Write to Serena only from the checkout where Serena started. A linked worktree must not call `write_memory`. The `reflect` skill states the rule.

## Check your result

You succeeded when all three hold:

1. Step 1 printed a table headed `Name Source Score Tokens Preview` with three `git/git-hooks-...` rows, each with source `Serena`.
2. Step 2 printed the heading `# Skill: Git-001 Pre-Commit Branch Validation`.
3. Step 4 printed the `systemMessage` line the first time and no stdout the second time.

If a step fails, look here first:

| Symptom | Cause | Fix |
|---|---|---|
| `search_memory.py` exits 1. | The query is empty or over 500 characters. | Shorten the query. |
| `search_memory.py` exits 2. | A path argument contains `..`, or `AI_AGENTS_REPO_ROOT` is not a directory. | Drop the path argument or fix the variable. |
| The hook prints nothing on the first run. | `AI_AGENTS_RETRO_NUDGE_THRESHOLD` is `0` or `off`, or the state directory sits inside a git repository. | Unset the variable. Point `XDG_STATE_HOME` at a directory outside any repository. |
| Stderr says `HOME unset, state root refused`. | The hook refuses to guess a state directory. | Set `HOME` or `XDG_STATE_HOME`. |
| The hook finds too few signals. | One correction or two praise or preference turns are the minimum. Only human-typed turns count. | Add turns with `"origin":{"kind":"human"}`. |

## Next

The next page in reading order is `template-first-authoring.md`. See the [training index](README.md) for every page.

This page relies on these sources. Read them for the full detail:

- [ADR-106](../../.project-toolkit/architecture/ADR-106-serena-only-memory-architecture.md): the Serena-only decision.
- [Memory README](../../.serena/memories/README.md): directory layout, index format, and size limits.
- [memory-search](../../src/claude/skills/memory-search/SKILL.md), [memory-gate](../../src/claude/skills/memory-gate/SKILL.md), and [memory-consolidate](../../src/claude/skills/memory-consolidate/SKILL.md): the memory skills.
- [reflect](../../src/claude/skills/reflect/SKILL.md) and [retrospective](../../src/claude/skills/retrospective/SKILL.md): the two learning skills.
- [invoke_reflect_nudge.py](../../.claude/hooks/Stop/invoke_reflect_nudge.py): the nudge, with its exit-code contract and patterns.
