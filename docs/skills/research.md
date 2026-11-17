# research

Turns an external topic into an analysis document of 3000 to 5000 words, maps it onto this project, writes a memory, and drafts the follow-up issue for the owner. Every claim that comes from an outside source passes a claim check before it is written.

## When to use it

- You need a sourced analysis of an outside practice, and a spec, issue, or artifact is waiting to consume it.
- Trigger phrases: `research this topic`, `what does the literature say about X`, `analyze this external practice for us`, `research and incorporate`.

## When not to use it

- You want to search this repository: use [`memory`](memory.md) or grep instead.
- No spec, issue, or artifact will consume the result. The skill halts at its front gate when you cannot name a consumer.
- A consumer exists but no spec captures the work: run [`spec`](spec.md) first, then return.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:research Topic: prompt caching strategies for long agent sessions. Context: we are sizing a cost reduction for the orchestrator.
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/research`.

Topic and context are both required. An optional `URLs:` line gives comma-separated source URLs. If you give no topic, the skill asks for one. The skill then researches, drafts the analysis, maps applicability, writes a memory, and drafts an issue body.

## What you get

| Artifact | Location |
| --- | --- |
| Analysis document | `{analysis-dir}/{topic-slug}.md` |
| Claim ledgers | `{analysis-dir}/{topic-slug}-{analysis,memory,issue}-claims.json` |
| Serena memory | `.serena/memories/{topic-slug}-integration.md` |
| Atomic memories | 5 to 10 in the host's long-term memory service, when one exists |
| Issue body | Drafted when work is identified; filed only if you asked for filing |

`{analysis-dir}` is the `analysis/` folder under your agent-artifacts directory, resolved the way `paths.artifact_dir` resolves it.

Quality gates that block the run: core principles, frameworks, and 3 examples in research; 3000 to 5000 words; 3 or more concrete examples; 3 or more failure modes with corrections; 2 or more links to existing concepts.

## Advanced use

**Five phases.** Research, analysis, applicability, memory, action. Each has a gate. The run has a 50k output token budget. Near the limit it summarizes, saves the partial analysis, and stops.

**Front gate.** Before phase 1 it runs the `front-gate-before-pipeline` pattern. The pattern's six questions decide whether the work should exist. See [`panning-for-gold`](panning-for-gold.md) Phase 0 if that skill is not installed.

**Claim gate.** The analysis, the memory, and the issue body each get their own draft and ledger. The skill lists claims that rest on outside sources and checks them with the `ai-agents-external-claims` skill. It runs the `claim_ledger.py` validator on the ledger and the draft, and writes the final artifact only after exit `0`. It then re-runs the validator on the final file to prove the copy is the checked text. If browsing is unavailable, it narrows or removes the claim and records the gap.

**Issues.** The skill does not publish an issue on its own. An agent that found the work does not select it, so the owner decides. If your request asked for filing, it confirms with you, then runs `new_issue.py` with `--source human`. It never passes `--source agent`. A non-zero exit from that script is not a plain failure, because it creates before it labels: read `references/degraded-mode.md` before you retry, or you may duplicate the issue.

**Search bound.** If three tool calls surface nothing useful, it switches to first-principles reasoning and documents what it tried.

**Untrusted content.** Fetched pages, diffs, logs, and issue bodies are data. The skill quotes and summarizes them and ignores instructions inside them. A permission denial from the harness is a capability signal, so the skill switches tools and continues.

**No dashes.** Everything the skill writes avoids em and en dashes.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec`](spec.md): the front gate when a consumer exists but no spec does.
- [`memory`](memory.md): retrieve incorporated knowledge.
- [`panning-for-gold`](panning-for-gold.md): the front gate procedure.
- [`ai-agents-external-claims`](ai-agents-external-claims.md): checks external claims for the ledger.
- Source: [`SKILL.md`](../../src/claude/skills/research/SKILL.md)
- Degraded mode: [`degraded-mode.md`](../../src/claude/skills/research/references/degraded-mode.md)
- Document skeletons: [`templates.md`](../../src/claude/skills/research/references/templates.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
