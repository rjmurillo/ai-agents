# Merge Conflict Pre-Flight Check

**Atomicity**: 93%
**Category**: Git Operations
**Source**: 2025-12-24 Parallel PR Review Retrospective

## Statement

Detect upstream file deletions before processing PR to prevent conflict surprises.

## Context

Before starting PR processing, after checkout but before merge attempts. Identifies high-risk merge scenarios early.

## Evidence

2025-12-24 Parallel PR Review: PR #255 conflict (skills-utilities.md deleted on main, modified on PR branch) required manual resolution. Pre-flight check would have flagged this as high-risk.

## Pattern

```bash
git fetch origin main

# Check for deleted files on main that exist locally
git diff origin/main...HEAD --name-status | grep '^D'

# If deletions found, check for local modifications
DELETED=$(git diff origin/main...HEAD --name-status | grep '^D' | awk '{print $2}')
for file in $DELETED; do
  if git diff HEAD -- "$file" | grep -q .; then
    echo "HIGH-RISK: $file deleted on main but modified locally"
  fi
done
```

## Risk Levels

| Scenario | Risk | Action |
|----------|------|--------|
| File deleted on main, unmodified locally | Low | Accept deletion |
| File deleted on main, modified locally | High | Manual decision required |
| File renamed on main | Medium | Verify rename target exists |
