| Keywords | File |
|----------|------|
| labeler negation pattern matcher all-globs selection | skill-labeler-001-negation-pattern-matcher-selection |
| labeler any matcher any-glob-to-any-file presence | skill-labeler-003-any-matcher |
| labeler all files matcher any-glob-to-all-files must match | skill-labeler-004-all-files-matcher |
| labeler all patterns matcher all-globs-to-any-file require | skill-labeler-005-all-patterns-matcher |
| labeler negation isolation all: block separate dedicated | skill-labeler-006-negation-pattern-isolation |
| labeler combined block all include exclude AND logic | labeler-combined-patterns |

| Matcher | Logic | Use When |
|---------|-------|----------|
| `any-glob-to-any-file` | ANY matches ANY | Simple presence check |
| `all-globs-to-all-files` | ALL match ALL | Negation patterns |
| `any-glob-to-all-files` | ANY matches ALL | All files must match |
| `all-globs-to-any-file` | ALL match ANY | Multiple patterns required |
