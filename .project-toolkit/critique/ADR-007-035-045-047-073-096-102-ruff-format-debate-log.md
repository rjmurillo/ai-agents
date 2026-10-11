# ADR Debate Log: ruff format applied to ADR code blocks

## Date: 2026-10-11

## Scope

Seven ADRs change only inside fenced `python` blocks, because `ruff format`
(0.16.9, pyproject settings) formats Python code blocks in Markdown:

- ADR-007, ADR-035, ADR-045, ADR-047, ADR-073, ADR-096, ADR-102

No frontmatter, status, prose, or link changes. Owner direction: apply the
formatter to the whole tree ("Everything counted"). The change does not touch
executable enforcement or a rule other gates read, so the reduced panel
(architect and critic) applies.

## Participants

- architect agent (read all 197 diff lines)
- critic agent (adversarial read of the same diff)

## Architect position

Verdict: accept. Every hunk is formatting only: quote style, trailing commas,
line wrapping, blank lines, and implicit string joins whose joined text is
byte-identical. No decision, status, cited contract, or runnable command
changes. Full panel not needed.

## Critic position

Verdict: accept ADR-007, ADR-035, ADR-045, ADR-047, ADR-073, ADR-096.

Verdict: needs-revision for ADR-102. Two code blocks quote validator logic from
inside a function body. The formatter dedents them, which removes the cue that
they are body fragments and breaks the byte-for-byte quote of the source.

## Outcome: Concluded with revision

Decision: accept the formatting for six ADRs. For ADR-102, a follow-up commit
on this branch restores the original indentation of both blocks by wrapping
them in `<!-- fmt:off -->` and `<!-- fmt:on -->` markers, which ruff honors.
After that commit ADR-102 differs from main only by those four comment lines.

Evidence the panel was run: architect and critic were invoked as separate
agents with the diff only, not the author's reasoning.
