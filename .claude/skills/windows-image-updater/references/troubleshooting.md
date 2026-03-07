# Troubleshooting: Windows Image Updater

Phase-by-phase error guide for the windows-image-updater skill.

## Phase 1: Package Update

### Package not found

**Symptom**: NuGet reports the target version does not exist.

**Resolution**:

1. Verify the version exists on the configured NuGet feed
2. Check feed authentication (PAT expiry, feed permissions)
3. Run `nuget list ConfigurationGeneration.AdoPipelineGeneration -AllVersions -Source {feed}` to list available versions

### Wrong packages.config location

**Symptom**: Package reference not found in expected file.

**Resolution**:

1. Search recursively: `find . -name "packages.config" -o -name "*.csproj" | xargs grep -l "ConfigurationGeneration"`
2. Some repos use `Directory.Packages.props` for central package management
3. Check for `.nuget/packages.config` at the solution root

## Phase 2: Dependency Resolution

### Version conflict loops

**Symptom**: Fixing one dependency creates a new conflict with another.

**Resolution**:

1. List all conflicting packages and their required version ranges
2. Find the intersection of compatible versions
3. Update all conflicting packages in a single pass
4. If no intersection exists, check whether a newer ConfigGen version resolves the conflict

### Feed authentication failure

**Symptom**: `401 Unauthorized` during restore.

**Resolution**:

1. Verify `nuget.config` contains valid feed credentials
2. Check PAT expiration date
3. Ensure the feed URL matches the organization's artifact feed
4. Try `dotnet nuget list source` to verify configured sources

### Transitive dependency pinning

**Symptom**: A transitive dependency is pinned to an incompatible version.

**Resolution**:

1. Check for explicit version pins in `Directory.Packages.props` or `packages.config`
2. Remove or update the pin to allow the required version range
3. Re-run restore and verify

## Phase 3: ConfigGen Execution

### ConfigGen not found

**Symptom**: ConfigGen executable not on PATH or in expected location.

**Resolution**:

1. Check `tools/ConfigGen/` directory
2. Run `nuget restore` to ensure ConfigGen package is downloaded
3. Check `.config/dotnet-tools.json` for tool manifest entries
4. Search: `find . -name "ConfigGen*" -type f`

### ConfigGen non-zero exit code

**Symptom**: ConfigGen exits with a non-zero code.

**Resolution**:

1. Read stderr output for specific error messages
2. Common causes:
   - Missing or invalid `configgen.json` configuration file
   - Schema validation failures in pipeline definitions
   - Missing environment variables required by templates
3. Fix the root cause and re-run. Do not proceed to Phase 4 with a failed ConfigGen run.

### ConfigGen generates no changes

**Symptom**: ConfigGen exits successfully but no YAML files are modified.

**Resolution**:

1. Verify the package version actually changes the image reference
2. Check if the repo uses a custom ConfigGen configuration that overrides image selection
3. Inspect the ConfigGen template files for hardcoded image references

## Phase 4: Image Verification

### Old image references remain

**Symptom**: `grep` still finds the old image string in YAML files after ConfigGen.

**Resolution**:

1. Check if the remaining references are in files not managed by ConfigGen
2. Look for hardcoded image references in:
   - `.azure-pipelines/` directories
   - `build/` directories
   - Custom pipeline templates
3. These files may need manual updates. Document them in the PR description.

### False positive matches

**Symptom**: grep matches the old image string in comments, documentation, or unrelated contexts.

**Resolution**:

1. Filter results to only `.yml` and `.yaml` files in pipeline directories
2. Exclude `CHANGELOG.md`, `README.md`, and documentation files
3. Use context-aware grep: `grep -n "image:.*ltsc2019" --include="*.yml" -r .`

## General

### Multiple solutions in one repository

Some repos contain multiple solutions with separate package configurations. Run each phase per solution, then verify across the entire repo in Phase 4.

### Rollback procedure

If the update causes pipeline failures that cannot be resolved:

1. Revert the package bump commit
2. Re-run ConfigGen with the original version
3. Verify the old image references are restored
4. Document the failure in the issue for investigation
