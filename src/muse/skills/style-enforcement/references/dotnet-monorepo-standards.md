---
source: wiki/concepts/Design Principles/dotNET Monorepo Standards.md
created: 2026-04-11
review-by: 2026-07-11
---

# .NET Monorepo Standards

Coding style, naming conventions, datetime handling, and project layout standards for .NET monorepos. Industry-aligned practices portable across projects.

## Coding Style

- Based on [.NET Runtime coding style](https://github.com/dotnet/runtime/blob/main/docs/coding-guidelines/coding-style.md)
- Enforced via `.editorconfig`
- StyleCop: `systemUsingDirectivesFirst`, `usingDirectivesPlacement: outsideNamespace`, newline at EOF
- `var` preferred everywhere; braces required; no `this.` qualification

## Naming Conventions

| Symbol | Convention |
|--------|-----------|
| Private static fields | `s_` prefix + camelCase |
| Instance fields | `_` prefix + camelCase |
| Constants | PascalCase |
| Public members | PascalCase |
| Locals/parameters | camelCase |

**Namespace convention**: `[Company].[Project].[Area].[...]`

### Avoid Shipping the Org Chart

Name components based on the problem they solve, not the team that owns them:

- Component solves a particular problem (e.g., `DataContracts` / `Protocols` not `Data.Definitions`)
- Ideally reusable as the primary way to solve that problem
- Ownership = creation, maintenance, and improving partner experience

## DateTime Handling

Prefer `DateTimeOffset` when designing new interfaces or classes.

| Field type | What to use |
|-----------|-------------|
| `DateTimeOffset` | Use directly |
| `DateTime` | Always `DateTime.UtcNow`, never `DateTime.Now` |
| `string` | `ToString("o")` for ISO-8601 round-trip format |

Specify all relevant local time zones or use UTC as standard. Do not assume one time zone in geodistributed teams.

## Project Layout

**Top-level directories**: `base/` (shared code), `build/` (build config), `docs/` (shared docs)

**Per-component convention**:

```text
$/COMPONENT
  .pipelines/
  docs/
  protos/       (optional)
  samples/      (optional)
  src/
  tests/
  dirs.proj
  README.md
```

## SDK-Style Projects

Modern .NET project format. Required for .NET Core/5+, also supports .NET Framework.

**SDK-style** (modern):

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.0</TargetFramework>
  </PropertyGroup>
</Project>
```

**Pre-SDK-style** (legacy): Presence of `ToolsVersion`, `ProjectGuid`, verbose XML imports. Absence of `Sdk` attribute.

**Detection rule**: `Sdk` attribute present = SDK-style. Absence + verbose XML = legacy.

### Migration

```bash
dotnet tool install -g upgrade-assistant
upgrade-assistant upgrade --operation feature.sdkstyle <path-to-csproj>
```

### Debugging Failed Migrations

Projects with custom MSBuild tasks/targets may not auto-migrate. Use:

- [MSBuildSummaryFiles](https://github.com/jeffkl/msbuildsummaryfiles) for diff-able compiler/build settings
- [MSBuild Binary Log Viewer](https://msbuildlog.com/) for deep build inspection

Run MSBuildSummaryFiles before/after migration and check for unexpected diffs.

## Style Enforcement Integration

These standards map to style-enforcement rules:

| Standard | Rule ID | Check |
|----------|---------|-------|
| `_` prefix on instance fields | STYLE-010 | Naming convention |
| `s_` prefix on static fields | STYLE-010 | Naming convention |
| `var` usage | editorconfig | `csharp_style_var_for_built_in_types` |
| Braces required | editorconfig | `csharp_prefer_braces` |
| No `this.` | editorconfig | `dotnet_style_qualification_for_field` |
| Newline at EOF | STYLE-005 | Final newline |
