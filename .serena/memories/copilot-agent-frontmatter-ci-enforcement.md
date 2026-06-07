# Copilot agent frontmatter: CI enforcement (issues #2491-#2497, #2500)

## Context
`.github/agents/*.agent.md` are Copilot custom agents. An unquoted plain-scalar
`description` embedding colon-bearing examples (`Context:`, `user:`) makes YAML
read the examples as mapping keys, so Copilot fails to load the agent. Six files
shipped broken (#2491-#2496, fixed in PR #2498 via block scalars).

## What was missing after #2498
- `scripts/validation/validate_copilot_agent_frontmatter.py` ran only in the local
  `pre_pr` gate, NOT in any CI workflow. A malformed file could still merge.
- No schema check beyond `name`; no YAML-parser-error in the failure message.

## Fix (PR for #2497 + #2500)
- Wired the validator into `.github/workflows/validate-generated-agents.yml` (it
  already triggers on `.github/agents/**`). CI now blocks the class.
- `find_malformed` now: raw-parses each block to surface the YAML parser error,
  requires `name`/`description` as non-empty strings, rejects non-string `tier`
  when present (tier is string-if-present, not hard-required, per #2500).
- Dropped a risky-plain-scalar lint: unreachable on parsing files (a colon-bearing
  plain scalar fails the parse check; a folded plain scalar has no newline).

## Gotcha
The maintainer refactored the validator post-#2498 to delegate `parse_frontmatter`
to `scripts/validation/yaml_utils._parse_yaml_frontmatter`, which swallows the YAML
error to `None`. To surface the parser error, `find_malformed` does its own
`yaml.safe_load` on the raw frontmatter block instead of relying on that helper.

Related: [[issue-triage-sweep-2026-06-04]]

## Related

- [copilot-hooks-observations](copilot-hooks-observations.md)
