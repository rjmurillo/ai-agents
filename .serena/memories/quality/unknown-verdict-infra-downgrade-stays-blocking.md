# Unknown verdict infra downgrade stays blocking

- Issue #4757 restricts the infra-only WARN downgrade to explicit infra verdicts.
- Any `*_INFRA=true` result is categorized as infrastructure, including
  `PASS`.
- A non-security `PASS` with the matching infra flag is a supported `WARN`
  path. Failure verdicts qualify for that downgrade only when they come from
  `FAIL_VERDICTS` or `DID_NOT_RUN`.
- Raw `UNKNOWN`, empty verdicts, and unrecognized tokens such as `FOOBAR` stay
  blocking. They indicate a parser or contract failure, not infrastructure.
- `merge_verdicts()` ranks `WARN` above `UNKNOWN`, so PR #4760 adds a post-merge
  guard. An infra-tagged unknown token cannot be masked by another agent's WARN.
- Regression coverage pins non-security `PASS + *_INFRA=true -> WARN`. It also
  pins infra-tagged security `DID_NOT_RUN` plus either `FOOBAR + WARN` or
  `UNKNOWN + WARN` to `UNKNOWN`.
