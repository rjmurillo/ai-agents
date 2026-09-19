# Evidence: atomic commit sequence

<!-- placement: evidence; reason: records a version control observation and migration destination, not an operating contract -->

## Observed evidence

Separate logical commits enabled selective rollback during a multi-file change.
The recorded example committed configuration before directory batches and
verified each batch before continuing.

## Migration disposition

The host Universal Rules own the logical, reviewable commit boundary. The build
and shipping skills own any task-specific commit sequence. This memory retains
the rollback rationale as evidence.
