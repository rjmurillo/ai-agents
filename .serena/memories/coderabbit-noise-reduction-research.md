# CodeRabbit Noise Reduction Research

## Key Findings (2025-12-14)

### No Severity Threshold Configuration

- CodeRabbit does NOT expose explicit severity threshold settings
- Cannot configure "only fail on Major/Critical issues"
- `fail_commit_status` only fires on review inability, not issue severity

### Primary Noise Controls

1. `profile: chill` (default) - reduces nitpicky feedback vs `assertive`
2. `path_instructions` with explicit IGNORE directives - most effective
3. `tone_instructions` (250 char max) - reinforces focus areas
4. Disable duplicate tools (e.g., `markdownlint: enabled: false`)

### Markdownlint Auto-Suppression

- Auto-disabled rules: MD004, MD012, MD013, MD025, MD026, MD032, MD033
- Auto-skips when markdownlint already runs in GitHub workflows

### Effective path_instructions Pattern

```yaml
path_instructions:
  - path: "**/*.cs"
    instructions: |
      FOCUS ON: Security, logic errors, race conditions
      IGNORE: style (dotnet format), naming (analyzers), XML docs
```

### Estimated Impact

- ~60% noise reduction with optimized configuration
- Preserves security/logic/bug detection

### Configuration File

Full analysis at: `.agents/analysis/001-coderabbit-noise-reduction-analysis.md`
