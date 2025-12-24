# Gemini Code Assist: config.yaml Schema

**Location**: `.gemini/config.yaml` (repository root)

## Complete Schema

```yaml
have_fun:
  type: boolean
  default: false
  description: Enables fun features (poems in PR summaries)

ignore_patterns:
  type: array of strings
  default: []
  description: Glob patterns for files to skip

memory_config:
  disabled:
    type: boolean
    default: false
    description: Disable persistent memory for this repo

code_review:
  disable:
    type: boolean
    default: false
    description: Disables Gemini from acting on PRs

  comment_severity_threshold:
    type: enum [LOW, MEDIUM, HIGH, CRITICAL]
    default: MEDIUM

  max_review_comments:
    type: integer
    default: -1 (unlimited)

  pull_request_opened:
    help:
      type: boolean
      default: false
    summary:
      type: boolean
      default: true
    code_review:
      type: boolean
      default: true
    include_drafts:
      type: boolean
      default: true
```

## Code Review Settings Reference

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| `code_review.disable` | boolean | false | Disable PR functionality |
| `code_review.pull_request_opened.code_review` | boolean | true | Review comments on PR open |
| `code_review.pull_request_opened.summary` | boolean | true | PR summary generation |
| `code_review.pull_request_opened.include_drafts` | boolean | true | Apply to draft PRs |
| `code_review.comment_severity_threshold` | enum | MEDIUM | Minimum severity |
| `code_review.max_review_comments` | integer | -1 | Max comments (-1=unlimited) |

## Recommended Configuration for AI Agent Repos

```yaml
code_review:
  disable: false
  pull_request_opened:
    code_review: true
    summary: false  # Disable summaries to avoid noise
    include_drafts: true
    help: false
  comment_severity_threshold: MEDIUM
  max_review_comments: -1

ignore_patterns:
  - ".agents/**"
  - ".serena/memories/**"
  - "**/*.generated.*"
  - "**/bin/**"
  - "**/obj/**"

have_fun: false
memory_config:
  disabled: false
```
