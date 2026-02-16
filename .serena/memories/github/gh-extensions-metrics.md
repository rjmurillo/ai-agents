# GitHub Extension: gh-metrics (hectcastro/gh-metrics)

## Skill-Ext-Metrics-001: PR Review Analytics

**Statement**: Use `gh metrics --repo` to calculate PR review metrics for team health analysis.

```bash
# Default metrics (last 10 days)
gh metrics --repo owner/repo

# Custom date range
gh metrics --repo owner/repo --start 2025-01-01 --end 2025-01-31

# Filter by author
gh metrics --repo owner/repo --query "author:username"

# Only weekdays (exclude weekends)
gh metrics --repo owner/repo --only-weekdays

# CSV export for further processing
gh metrics --repo owner/repo --csv > metrics.csv

# Current repo (uses git remote)
gh metrics
```

## Metrics Calculated

| Metric | Description |
|--------|-------------|
| Time to First Review | PR creation to first review |
| Feature Lead Time | First commit to merge |
| First to Last Review | First review to final approval |
| First Approval to Merge | First approval to merge |

## Use Cases

- Identify review bottlenecks
- Track team velocity
- Benchmark sprint performance
- Generate reports for stakeholders

## Related

- [gh-extensions-anti-patterns](gh-extensions-anti-patterns.md)
- [gh-extensions-combine-prs](gh-extensions-combine-prs.md)
- [gh-extensions-grep](gh-extensions-grep.md)
- [gh-extensions-hook](gh-extensions-hook.md)
- [gh-extensions-maintenance](gh-extensions-maintenance.md)
