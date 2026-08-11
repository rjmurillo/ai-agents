# Unknown verdict infra downgrade stays blocking

- Issue #4757 restricts the infra-only WARN downgrade to explicit infra verdicts.
- Explicit infra verdicts are tokens from `FAIL_VERDICTS` or `DID_NOT_RUN` with
  the matching `*_INFRA=true` flag.
- Raw `UNKNOWN`, empty verdicts, and unrecognized tokens such as `FOOBAR` stay
  blocking. They indicate a parser or contract failure, not infrastructure.
- `merge_verdicts()` ranks `WARN` above `UNKNOWN`, so PR #4760 adds a post-merge
  guard. An infra-tagged unknown token cannot be masked by another agent's WARN.
- Regression coverage pins both `DID_NOT_RUN + FOOBAR + WARN -> UNKNOWN` and
  `DID_NOT_RUN + WARN -> WARN`.
