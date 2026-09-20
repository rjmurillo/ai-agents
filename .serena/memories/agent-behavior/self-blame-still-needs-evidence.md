# Evidence: self-blaming conclusion without disposition evidence

<!-- placement: evidence; reason: records a historical attribution error and its correction, not an operating contract -->

Source: PR #4290, PR #4302, and issue #4285.

## Observed evidence

An analysis treated the diff in a closed pull request as accepted evidence. The
pull request author later described the change as the wrong fix, and the
original suppression remained on the target branch. The analysis had checked
content but not disposition.

## Migration disposition

The host Universal Rules own the evidence bar for self-blame and external
attribution. The original incident remains useful because it identifies the
failure mode: a self-critical conclusion can skip the same verification that a
self-protective conclusion would receive.
