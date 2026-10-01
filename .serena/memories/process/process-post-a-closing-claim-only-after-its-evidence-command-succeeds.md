# Post a closing claim only after its evidence command succeeds

## What happened

On 2026-09-29 the orchestrator closed #5488 with a comment saying "a grep of .claude/skills and scripts finds no lease code". The grep in the same command failed first under zsh with `no matches found: --include=*.py`. The close ran anyway. A later check showed the claim was true, so the comment was right by luck, not by evidence.

An absence claim from a failed probe is unproven. It reads the same as one from a passing probe, and nobody rechecks an absence.

## Practice

Run the evidence command alone and read its exit status and output. Post the close comment only when the probe ran cleanly. Quote the glob (`--include='*.py'`) or use the Grep tool, since zsh expands an unquoted glob before grep sees it. Chain the close behind the probe with `&&` when both share one command.

## Source

P1 sweep 2026-09-29, issue #5488 (closed as fixed by #5697). Related: `.claude/rules/universal.md` MUST NOT 9 on absence claims.
