# prose-self-check

Checks the prose an agent is about to write for AI-vernacular tells. It runs two scripts, then a judgment pass on whether each paragraph says anything. It audits the agent's own output, not text a human wrote.

## When to use it

- Before the agent writes a session-log narrative, ADR context section, retrospective, PR body, issue body, design doc, or agent-authored comment.
- You want to know whether a draft reads as AI-written.
- Trigger phrases: `prose self-check`, `audit my writing for AI tells`, `does this read as AI-written`, `check this prose before I send it`.

## When not to use it

- You want to check code style: use [`style-enforcement`](style-enforcement.md).
- You want to rewrite text a human wrote. This skill does not touch human-authored text.
- You want to check documentation facts: use [`doc-accuracy`](doc-accuracy.md).

Skip it for pure data or config files and one-line acknowledgements.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:prose-self-check`. The agent loads it when your request matches, and [`spec-generator`](spec-generator.md) runs it before it emits a prose artifact. To ask for it by name, say:

```text
Use the prose-self-check skill on docs/adr/ADR-120-retry-policy.md before I open the PR.
```

The skill lints the file, measures sentence rhythm, fixes what it finds, and reports the changes layer by layer.

## What you get

A passing artifact has all of these:

- `prose_lint.py` exits 0: no dashes, no high-signal lexical tells, no contrast framing, no manufactured trailing offer, and no signposting opener.
- Every `info` finding was judged by Layer 4 rather than scrubbed.
- Sentence length varies, or you have a reason to keep it flat.
- Every paragraph makes a claim a reader could push back on.

Each lint finding prints as `FILE:LINE:COLUMN: SEVERITY: KIND: MATCH (note)`. Every run ends with what it examined, such as `0 findings in N prose line(s) of M in K file(s)`. A code fence that never closes is reported as a high-severity `unterminated_fence` finding.

## Advanced use

The four layers run in order of reader trust, not ease of detection:

| Layer | What it checks | Who runs it |
| --- | --- | --- |
| 1. Lexical | Em and en dashes, model-identity phrases, banned vocabulary. High-signal findings fail the run. Low-signal words show as `info`. | `prose_lint.py` |
| 2. Structural | Contrast framing (`contrast_framing`), manufactured trailing offers (`trailing_offer`), signposting openers (`signposting`). | `prose_lint.py` |
| 3. Distributional | Sentence-length spread (flat rhythm) and a concreteness count. A proxy, not a gate. | `burstiness.py` |
| 4. Semantic | Name the one disagreeable claim in each paragraph. If you cannot, give it a claim with evidence or cut it. | You |

Two shapes stay manual: rule-of-three padding, and inline-header lists where the bold label adds nothing. A clean `prose_lint.py` exit clears Layers 1 and 2 only. It says nothing about whether the prose says anything. The banned-word list is not copied into the skill. The script reads it from the voice rule at run time.

Run the scripts from the root of a checkout of this repository:

```bash
uv run python .claude/skills/prose-self-check/scripts/prose_lint.py draft.md notes.md --json
uv run python .claude/skills/prose-self-check/scripts/burstiness.py draft.md
```

| Script | Flags | Exit codes |
| --- | --- | --- |
| `prose_lint.py` | One or more `files` (`-` reads stdin), `--rules RULES`, `--json` | 0 no high-severity findings, 1 at least one, 2 a named file cannot be read |
| `burstiness.py` | One `file`, `--json` | 0 analyzed (with or without a flat-rhythm warning), 2 missing or unreadable file |

`burstiness.py` prints sentence count, word count, mean and standard deviation of sentence length, coefficient of variation, a concreteness count, and a flat-rhythm warning when variance is low and there are at least four sentences. When no copy of the voice rule is reachable, `prose_lint.py` warns on stderr and runs the dash and structural checks only.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec-generator`](spec-generator.md): runs this skill before it emits any prose artifact.
- [`style-enforcement`](style-enforcement.md): code style, which this skill leaves alone.
- [`prompt-engineer`](prompt-engineer.md): authors prompts but does not audit emitted prose.
- [`doc-accuracy`](doc-accuracy.md): factual accuracy of docs, separate from vernacular.
- Source: [`SKILL.md`](../../src/claude/skills/prose-self-check/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
