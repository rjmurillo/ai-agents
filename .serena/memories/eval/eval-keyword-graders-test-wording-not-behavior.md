<!-- placement: evidence; reason: records one measured eval incident and its cause, not a procedure -->
# Keyword graders test prompt wording, not behavior

## Observation

PR #6097 changed the orchestrator prompt for issue #5766. Its first live ADR-057 run
failed 15 of 17 new scenarios on both the old and the new prompt.

The prompt was not the cause. Most graders were keyword checks that demanded
phrases copied word for word from the new prompt text. A model that did the right
thing in its own words failed. Scenarios S15, S16, and S18 also had bad setups.

After the graders checked behavior and the scenarios were fixed, the gate passed.
The score moved from 83.9% to 100% at a7e6e1038.

## Why it matters

A failing score that hits both baseline and candidate equally points at the grader
first. A keyword grader built from the prompt under test measures recall of that
prompt's wording. It cannot tell a behavior regression from a paraphrase.

The same gap applies to text-pinning unit tests. A test that asserts a prompt
file contains a sentence proves the sentence exists. It does not prove a model
acts on it. The live ADR-057 eval (`scripts/eval/eval-prompt-change.py`) is the
evidence for behavior.

## Open items seen in the same run

- S17 returned PARSE_ERROR from truncated JSON output.
- S11 scored 0 of 3 on both sides, before and after the change.

## Source

PR #6097, issue #5766, owner decision D19 (hold and diagnose), 2026-10-03.
