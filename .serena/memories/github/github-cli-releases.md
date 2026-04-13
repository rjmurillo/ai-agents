# GitHub CLI Releases

## Skill-GH-Release-001: Release Creation (95%)

**Statement**: Use `gh release create` with `--generate-notes` for auto-changelog; attach assets with `#` for labels.

```bash
# Create with auto-generated notes
gh release create v1.2.3 --generate-notes

# Create with notes file
gh release create v1.2.3 -F CHANGELOG.md

# Create draft release
gh release create v1.2.3 --draft

# Create prerelease
gh release create v1.2.3-beta.1 --prerelease

# Upload assets with display labels
gh release create v1.2.3 'app.zip#Application Bundle'

# Create from specific commit
gh release create v1.2.3 --target abc1234
```

## Skill-GH-Release-002: Release Asset Management (93%)

**Statement**: Use `gh release download` with `--pattern` for selective downloads; `gh release upload` for adding assets.

```bash
# Download by pattern
gh release download --pattern '*.deb'

# Download source archive
gh release download v1.2.3 --archive=zip

# Upload additional assets
gh release upload v1.2.3 new-asset.zip

# Upload with display label
gh release upload v1.2.3 'checksums.txt#SHA256 Checksums'

# Overwrite existing asset
gh release upload v1.2.3 updated.zip --clobber

# Delete with associated tag
gh release delete v1.2.3 --yes --cleanup-tag
```

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
