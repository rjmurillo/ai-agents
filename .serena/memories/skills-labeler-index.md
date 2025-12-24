| Keywords | File |
|----------|------|
| negation pattern matcher selection all-globs-to-all-files anti-pattern | skill-labeler-001-negation-pattern-matcher-selection |
| negation isolation separate dedicated block AND logic | skill-labeler-006-negation-pattern-isolation |
| any-glob-to-any-file presence check simple single | skill-labeler-003-any-matcher |
| any-glob-to-all-files every changed file must match | skill-labeler-004-all-files-matcher |
| all-globs-to-any-file multiple patterns required AND | skill-labeler-005-all-patterns-matcher |
| combined block include exclude merge positive negative | labeler-combined-patterns |
| Matcher | Logic | Use When |
|---------|-------|----------|
| `any-glob-to-any-file` | ANY matches ANY | Simple presence check |
| `all-globs-to-all-files` | ALL match ALL | Negation patterns |
| `any-glob-to-all-files` | ANY matches ALL | All files must match |
| `all-globs-to-any-file` | ALL match ANY | Multiple patterns required |
