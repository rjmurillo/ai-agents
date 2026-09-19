# Evidence: agent error recovery incidents

<!-- placement: evidence; reason: records historical failures and migration rationale, not an operating contract -->

Source: Session 2, 2026-04-10.

## Observed evidence

- A push or commit failure stopped the agent. The user had to report the halt.
- Two commits failed because session logs omitted required fields.
- A valid log from the same branch showed the required structure.

## Migration disposition

The host Universal Rules own failure classification, bounded retry, refusal
handling, unavailable results, no fabrication, and schema observation. The
session log schema and its validator own field shape. This memory retains the
incident evidence and no longer acts as a policy source.
