# Upstream provenance

This skill forks `skills/takeover/SKILL.md` from [tstack](https://github.com/t3dotgg/tstack).
Theo Browne holds the upstream copyright.
The [MIT license](../LICENSE) ships with this skill.

The reconciliation baseline is `11e37a74d0a6868c121cd0910ab2b3bd9873b92a`, fetched 2026-11-16.
That revision is a comparison base, not an upstream freshness claim.

## Local adaptations

The body keeps the upstream text, reorganized under Triggers, Process, and Verification headings.
The Triggers table, Verification checklist, Anti-Patterns, and Extension Points are local additions.
The repository skill validator requires those sections.
The body also replaces the tstack skills this catalog lacks.

| Upstream reference | Local replacement |
|---|---|
| `modernize` | Prose step to update against the intended base, plus the merge-resolver agent for conflicts |
| `file-pr` | `push-pr` |
| `babysit-pr` | `github` skill for checks, `pr-comment-responder` for review threads |
| `leaving-pr-comments` | `pr-comment-responder` |

The frontmatter adds a version, license, routing metadata, and "Do NOT use" boundaries.

Do not overwrite this fork with upstream files.
Diff upstream against the baseline, then apply each change to the adapted text.
