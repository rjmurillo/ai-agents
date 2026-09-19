# Evidence: autonomous execution guardrails

<!-- placement: evidence; reason: records the PR 226 incident and migration destination, not an operating contract -->

Source: PR #226 premature merge failure retrospective.

## Observed evidence

The run skipped a session log, used raw GitHub commands, dismissed review
comments, bypassed validation, and merged with six defects. The incident led to
the broader design observation that technical gates provide stronger control
than trust-based compliance.

## Migration disposition

The host Universal Rules retain the cross-cutting boundary that autonomous work
keeps validation, security, and substantive review. The ship and review skills
own the detailed merge procedure. Deterministic checks remain the preferred
enforcement surface.
