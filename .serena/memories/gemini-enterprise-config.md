# Gemini Code Assist: Enterprise/Multi-Repo Configuration

## Enterprise Version

**Group-Level Configuration**:
- Managed via Google Cloud console
- Apply settings to Developer Connect connection groups
- Set organization-wide style guides

## Configuration Precedence

| Setting Type | Behavior |
|--------------|----------|
| `config.yaml` | **Overrides** group settings |
| "Improve response quality" | Can only be **disabled** in repo, not enabled |
| `styleguide.md` | **Combined** with group style guide (not replaced) |

## Consumer Version

- Toggle settings for all repositories via Code review page
- Per-account settings (no group-level)

## Key Enterprise Differences

1. **Group policies** can enforce minimum security thresholds
2. **Style guides merge** - repo-specific rules add to organization rules
3. **Some settings locked** - repo cannot enable disabled features
4. **Centralized management** - Cloud console for bulk config
