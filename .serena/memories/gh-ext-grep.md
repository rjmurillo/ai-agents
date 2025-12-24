# GitHub Extension: gh-grep (k1LoW/gh-grep)

Code search across repositories via GitHub API.

## Skill-Ext-Grep-001: Search Code Across Repositories

**Statement**: Use `gh grep` with `--include` filter for performance; searches via GitHub API.

**Performance Warning**: This tool is SLOW because it uses GitHub API. Always use `--include` to filter files.

```bash
# Search in specific repo
gh grep "TODO" --repo owner/repo

# Search with owner scope (all org repos)
gh grep "deprecated" --owner myorg

# Filter by file pattern (CRITICAL for performance)
gh grep "FROM.*alpine" --owner myorg --include "Dockerfile"
gh grep "password" --repo owner/repo --include "*.py"

# Exclude files/directories
gh grep "secret" --repo owner/repo --exclude "*test*"
gh grep "api_key" --repo owner/repo --exclude "*.md"

# Case insensitive
gh grep -i "fixme" --repo owner/repo

# Show line numbers
gh grep -n "TODO" --repo owner/repo

# Output with GitHub URLs (clickable)
gh grep "security" --repo owner/repo --url

# Show only matching parts
gh grep -o "v[0-9]+\.[0-9]+\.[0-9]+" --repo owner/repo

# Count matches only
gh grep -c "TODO" --repo owner/repo

# Show only filenames
gh grep --name-only "pattern" --repo owner/repo

# Show only repo names
gh grep --repo-only "pattern" --owner myorg

# Search specific branch
gh grep "feature" --repo owner/repo --branch develop

# Search specific tag
gh grep "version" --repo owner/repo --tag v1.0.0
```

## Use Cases

- Security audits (find hardcoded secrets patterns)
- Dependency audits (find specific import patterns)
- License compliance (find license headers)
- Migration planning (find deprecated API usage)
