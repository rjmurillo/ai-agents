# GitHub Actions Labeler Domain Index

**Purpose**: Route to atomic skills for actions/labeler configuration, matcher types, and negation patterns.

**Source**: PR #226, PR #229 retrospective

## Activation Vocabulary

| Keywords | File |
|----------|------|
| labeler negation pattern matcher all-globs exclude isolation | labeler-negation-patterns |
| labeler matcher any-glob all-files all-globs selection type | labeler-matcher-types |
| labeler combined block all include exclude AND logic | labeler-combined-patterns |

## Domain Statistics

- **Skills**: 6 core skills
- **Evidence**: PR failures → working solution

## Matcher Type Quick Reference

| Matcher | Logic | Use When |
|---------|-------|----------|
| `any-glob-to-any-file` | ANY matches ANY | Simple presence check |
| `all-globs-to-all-files` | ALL match ALL | Negation patterns |
| `any-glob-to-all-files` | ANY matches ALL | All files must match |
| `all-globs-to-any-file` | ALL match ANY | Multiple patterns required |

## See Also

- `.github/labeler.yml` - Working configuration
- `skills-github-workflow-patterns` - Workflow patterns
