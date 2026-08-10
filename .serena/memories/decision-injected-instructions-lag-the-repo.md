# Decision: the harness-injected instruction copy is a cache, not the rule

## Statement

Read a rule's repo file before acting on the injected copy; it lags
(`knowledge-persistence.md:21`).

## Question

A rule from `.claude/rules/` or `AGENTS.md` appears verbatim in the always-on
context the harness injects at session start. You are about to act on it. Do you
need to open the file?

## Conventional answer

No. The injected block is the project's own instruction text, delivered by the
harness for exactly this purpose. Opening the file to re-read what is already in
context is the kind of redundant tool call that wastes turns.

## First-principles position

The injected block is a build-time snapshot, not a live read. The repository
moves under it: a rule can be rewritten, reversed, or superseded by an ADR after
the snapshot was cut, and nothing invalidates the copy in context. Two artifacts
that look identical are a canonical file and a cache with no expiry.

The failure mode is worse than a stale fact. Acting on the snapshot produces a
change that is confidently wrong in the exact direction the repo has already
rejected, and it arrives dressed as compliance with project policy.

## Evidence

Measured on 2026-08-05 in `~/src/scratch/wt-retro`. The injected copy of
`knowledge-persistence.instructions.md` carried:

> **Bump the plugin manifests**. [...] a rule change MUST bump both
> `.claude-plugin/plugin.json` manifests to the same strictly-greater version
> (see `.claude/rules/plugin-version-bump.md`, parity gate).

The repo file, `.claude/rules/knowledge-persistence.md:21`, says the reverse:

> **Leave the plugin manifests alone**. [...] the manifests carry no `version`
> field [...] Adding a `version` back fails
> `build/scripts/validate_plugin_version_bump.py` (see
> `.claude/rules/plugin-version-bump.md` and ADR-092).

The snapshot cites `plugin-version-bump.md` as its authority while stating the
opposite of what that file says. `plugin-version-bump.md` closes with a section
titled "If instructions say to bump, they are stale."

Not an isolated line. The same snapshot's `AGENTS.md` block reads
`Bump plugin manifest`; the repo's `AGENTS.md:24` reads
`No manifest version (ADR-092)`. Two independent instances of the same reversal
in one snapshot.

Cost had it been believed: adding a `version` key to three manifests, which
fails the gate on push, plus an "on-contact fix" reverting a correct rule to its
superseded form.

## Decision

Before editing a file because a rule requires it, `grep` the rule's own text in
its repo file. One `grep` on the governing term, not a re-read of the whole file.
Prefer the repo file whenever the two disagree; the injected copy has no way to
be newer.

This is the general case of the same asymmetry `decision-agent-files-are-not-canonical.md`
records inside the tree. That memory answers which repo file is canonical among
repo files. This one answers a prior question: whether the text in front of you
is a repo file at all.

## Scope

Applies to any always-on context block: `AGENTS.md`, `CLAUDE.md`,
`copilot-instructions.md`, `.github/instructions/*.instructions.md`, and
`.claude/rules/*.md` as reproduced by the harness. Does not apply to files read
with a tool during the session; those are live.
