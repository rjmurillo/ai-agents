| Keywords | File |
|----------|------|
| labeler negation pattern matcher all-globs exclude isolation | labeler-negation-patterns |
| labeler matcher any-glob all-files all-globs selection type | labeler-matcher-types |
| labeler combined block all include exclude AND logic | labeler-combined-patterns |
| Matcher | Logic | Use When |
|---------|-------|----------|
| `any-glob-to-any-file` | ANY matches ANY | Simple presence check |
| `all-globs-to-all-files` | ALL match ALL | Negation patterns |
| `any-glob-to-all-files` | ANY matches ALL | All files must match |
| `all-globs-to-any-file` | ALL match ANY | Multiple patterns required |
