# ADR-102 Debate Log: fmt markers after ruff format

## Date: 2026-10-11

## Scope

ADR-102 gains four HTML comment lines: `<!-- fmt:off -->` and `<!-- fmt:on -->`
around two code blocks. The blocks quote validator logic from inside a function
body. The first formatting pass dedented them, which the critic flagged in the
panel recorded in ADR-007-035-045-047-073-096-102-ruff-format-debate-log.md.

## Participants

- critic agent (raised the objection in the earlier panel)
- author (applied the revision)

## Critic position

Verdict: needs-revision on the dedent. Restoring the original indentation makes
the blocks quote the source again.

## Outcome: Accepted

Decision: accepted. The markers restore both blocks to their text on main. The
diff of ADR-102 against main is now exactly four comment lines, with no change
to a decision, status, contract, or command. The fix was checked by diffing
ADR-102 against main, not by a second panel.
