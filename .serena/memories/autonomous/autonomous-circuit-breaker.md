# Evidence: repeated autonomous failures

<!-- placement: evidence; reason: records a failure sequence and migration destination, not an operating contract -->

Source: PR #760.

## Observed evidence

The change accumulated 38 commits, three user patches, and 54 review comments.
The sequence included a suppression attempt, an incomplete fix, and repeated
work on the same issue. The evidence showed rising cost and declining user
confidence after the early failed attempts.

## Migration disposition

The host Universal Rules now cover stopping repeated strategies after three
failed attempts and reporting the evidence. Terminal task semantics remain with
issue #5404.
