# ai-agents-external-claims

Checks outside claims against their primary source before they land in a repo artifact. It covers numbers, attributions, and third-party citations. It also records contracts that code depends on.

## When to use it

- A number, attribution, or vendor statement from outside the repo is about to enter an ADR, retro, memory, PR description, session log, or external deliverable.
- The author has a stake in the framing, such as a vendor post or founder pitch.
- The claim is a round number ("over 1000"), a named authority ("Gartner says"), or a stat that cites a stat that cites a stat.
- Trigger phrases: `verify an external claim`, `check a vendor number`, `is this stat real`, `validate a third-party citation`.

## When not to use it

- You want to prove an idea that started inside the repo: use [`ai-agents-research-methodology`](ai-agents-research-methodology.md).
- You want to decide what counts as test evidence for a change: use [`ai-agents-validation-and-qa`](ai-agents-validation-and-qa.md).
- You want to scan for command injection: use [`security-scan`](security-scan.md).
- You want to stop a deliverable that no consumer asked for: use [`avoiding-manufactured-work`](avoiding-manufactured-work.md).

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:ai-agents-external-claims`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the ai-agents-external-claims skill to verify the "over 1000 stars" claim in docs/vendor-comparison.md against the repository host.
```

The skill names the claim, fetches the primary source, compares exact values, and keeps only what the source supports.

## What you get

For each claim, you get one of two outcomes: the claim stated at the confidence the primary source supports, with an inline citation, or the claim removed. The skill does not leave a sentence like "would be N if X corroborates" in an artifact.

In research mode, you also get a JSON claim ledger. Each entry has a `disposition`:

| Field | Values |
| --- | --- |
| `source.kind` | `primary`, `secondary` (say why no primary exists), or `none` |
| `confidence` | `high`, `medium`, `low`, `none` |
| `disposition` | `verified`, `narrowed`, `qualified`, `removed` |

`verified` needs a primary source and high or medium confidence. A secondary source caps confidence at medium. Source kind `none` allows only `qualified` or `removed`. A kept time-sensitive claim says "as of" and records the source date.

## Advanced use

The process has four phases:

1. Name the claim and its one primary source. A host page or registry API beats a blog. A paper beats a vendor landing page. Vendor docs alone are not a primary source for runtime behavior. Use an empirical probe at a pinned version, through [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md).
2. Fetch the source and compare exact number, attribution, and scope. Follow any chain of citations to its origin. Quote repo-internal claims verbatim with a path.
3. Weigh the source's stake. Self-favorable claims need a neutral source first.
4. Walk the gate or file conservative. Run the check now, or state only what you can defend and drop the rest.

The [`research`](research.md) skill invokes this one before each durable write. It activates when the text makes `vendor`, `api`, `statistic`, `legal`, `project-status`, or `comparative` claims. It skips, and still writes a ledger with the reason, when every fact comes from this repository.

Validate a ledger against a draft from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-external-claims/scripts/claim_ledger.py --ledger claims.json --artifact report.draft.md
```

| Exit code | Meaning |
| --- | --- |
| 0 | The ledger passed. Copy the draft to its final location and recheck it. |
| 1 | Defects, listed in the JSON on stdout. Fix the ledger or the draft and rerun. |
| 2 | A file is unreadable, the ledger is not JSON, or arguments are bad. |

With `--artifact`, the validator refuses a kept final wording missing from the draft, a removed claim still present, a narrowed or qualified claim whose original sentence is still present, and a `skip` decision over a draft that cites an outside URL.

For contracts that code depends on, the skill persists one `external-contract` record beside the consuming file. Fields: `source`, `version`, `evidence` (`documentation`, `specification`, or `empirical`), `verified` (ISO date), `purpose` (at most 200 characters), `reverify` (required for `empirical`), and optional `capability`. Persist only when code relies on a vendor limit, a version-specific API, a standard, or a probed behavior, and nothing executable represents it. The repository script `check_external_contracts.py` (not shipped in the plugin) finds consumers with `--source` and lists unchecked records with `--stale-before`.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`research`](research.md): invokes this skill at its claim gate.
- [`avoiding-manufactured-work`](avoiding-manufactured-work.md): the same reward-bias root cause, on the deliverable side.
- [`ai-agents-research-methodology`](ai-agents-research-methodology.md): for ideas that start inside the repo.
- Source: [`SKILL.md`](../../src/claude/skills/ai-agents-external-claims/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
