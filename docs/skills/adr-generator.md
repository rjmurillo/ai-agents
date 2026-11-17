# adr-generator

Writes a new Architecture Decision Record (ADR) for a decision you describe. It finds where your ADRs live, copies their template and numbering, drafts the record, and runs exit gates before it hands the file to `adr-review`.

## When to use it

- You need to document a technical decision, with its context, alternatives, and consequences.
- You want to capture the rationale so future maintainers can revisit a choice.
- You are creating an ADR-like file under `.project-toolkit/architecture/`, `docs/adr/`, `docs/architecture/`, `docs/decisions/`, or `architecture/decisions/`.
- You say `write an ADR`, `create an ADR`, `generate ADR for`, `document these design choices`, or `record why we chose this`.

## When not to use it

- You want to debate or review an ADR that exists: use [`adr-review`](adr-review.md) instead.
- The decision is a minor implementation detail, trivially reversible, and local. The skill suggests you skip the ADR.
- You are changing an existing system and need its history first: run [`chestertons-fence`](chestertons-fence.md), which this skill also calls for prior art.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:adr-generator write an ADR for switching from REST to gRPC
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/adr-generator`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /adr-generator skill to ...`.

The skill asks for any missing input: title, context, the decision with its rationale, at least two alternatives, and stakeholders. It then writes the ADR file and runs the exit gates.

## What you get

- One ADR file in the destination directory, named to match the existing ADRs (for example `ADR-053-authentication-strategy.md` or `0053-authentication-strategy.md`). The slug is lowercase kebab-case, three to five words.
- Status set to `proposed`. Only an `adr-review` consensus changes it.
- Alternatives with pros and cons, and at least one negative consequence.
- A claims ledger at `.project-toolkit/critique/ADR-NNN-claims-ledger.md`, written during the exit gates.

When the destination uses this repository's canonical template, the file starts with YAML frontmatter:

| Field | New ADR value |
| --- | --- |
| `id` | `ADR-NNN`, the number the skill picked |
| `status` | `proposed` |
| `date` | Today, last-updated |
| `decision-makers` | `[]` |
| `supersedes` | `[]` |
| `superseded-by` | `null` |
| `explainer` | `null`. The skill records a supplied link as text and never fetches it. |
| `implemented` | `false`. It flips to `true` at the first merged change. |

## Advanced use

The skill runs six phases.

| Phase | What happens |
| --- | --- |
| G1 Gather | Collects the inputs. Runs the ASR significance test and the START definition of ready. Starts prior art research when the decision changes an existing system. |
| G2 Research | Finds the ADR directory, reads two or three existing ADRs to detect the template, and picks the next number. |
| G3 Generate | Fills the detected template. |
| G4 Validate | Checks the draft against the quality checklist. |
| G5 Save | Writes the file with the matching name and number. |
| G6 Hand off | Refreshes the ADR index, then passes the ADR and ledger to `adr-review`. |

Template detection supports MADR, Nygard, Alexandrian, and the project canonical template. If no ADRs exist, the skill asks you to pick one from the catalog. If you name a location, the skill uses it.

> [!NOTE]
> `adr-review` auto-triggers only on uppercase `ADR-*.md` file names. If your existing ADRs use lowercase names, the skill warns you that automatic review will not fire.

In this repository, find the next free number with the helper the skill names. The same check runs as a merge-time CI gate:

```bash
uv run python scripts/validation/check_adr_uniqueness.py --print-next
```

The exit gates run in order against the saved draft. Each result is `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, or `FAILED`.

1. Claims ledger: one row per factual claim, with kind, command, and result.
2. Documentation accuracy: the [`doc-accuracy`](doc-accuracy.md) skill, Phase 4.
3. Self-consistency: each Decision item against the others and against Consequences.
4. Refuting seat: one `analyst` agent refutes only the claims ledger against the repository tree.
5. ADR review hand-off: the ledger path and contents go to `adr-review`.

The skill bundles no scripts. The index refresh in G6 runs only in a checkout of `rjmurillo/ai-agents`. Any other checkout skips it.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`adr-review`](adr-review.md): validates the ADR this skill writes, through a multi-agent debate.
- [`chestertons-fence`](chestertons-fence.md): investigates why an existing system looks the way it does.
- [`doc-accuracy`](doc-accuracy.md): checks documentation claims against source in exit gate 2.
- [`analyst`](../agents/analyst.md): runs the refuting seat in exit gate 4.
- Source: [`SKILL.md`](../../src/claude/skills/adr-generator/SKILL.md)
- References: [`adr-templates-catalog.md`](../../src/claude/skills/adr-generator/references/adr-templates-catalog.md), [`quality-checklist.md`](../../src/claude/skills/adr-generator/references/quality-checklist.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
