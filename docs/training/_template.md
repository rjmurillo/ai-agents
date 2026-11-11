# Title: say the outcome, for example "Install the toolkit on Codex"

<!--
Copy this file to docs/training/<kebab-case-name>.md. Delete every comment.
Rules are in docs/training/README.md. Short version:
- Keep these five headings, in this order. Add no others.
- No YAML front matter. The wiki shows it as text.
- Link to skills, ADRs, and scripts. Do not copy them.
- Show only commands you ran on main. Paste the output you got.
- Repo commands use `uv run python`, never bare `python3`.
- Write "you" and "we". Keep sentences short. No em or en dashes.
-->

## Goal

State the one result the reader will have at the end, and how they will know. Name who this page is for.

## Before you start

List what the reader needs: tools, access, and earlier pages. Link each earlier page.

## Steps

1. Say what to do in one sentence.

   ```bash
   uv run python scripts/example.py --flag
   ```

   Show the output you got:

   ```text
   expected output here
   ```

2. Continue. One action per step.

## Check your result

Give one command or observation that proves the Goal is met. Show the exact output. Say what a failure looks like and where to look first.

## Next

Link the next page in reading order. Then list the reference sources this page relies on, for example a skill (`.claude/skills/<name>/SKILL.md`), an ADR, or a script.
