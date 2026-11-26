# aspire.dev Site-Specific Rules

These rules apply only on aspire.dev. They are the aspire-only parts of the
upstream common issues, cross-referencing, and testing references. The generic
parts live in the skill's top-level references.

## Links and page moves

- Link with absolute paths from the docs root: `[Service Defaults](/fundamentals/service-defaults/)`.
- Known wrong targets from past PR feedback:
  - `/get-started/setup-and-tooling/` should be `/get-started/prerequisites/`.
  - `/reference/cli/` for CLI installation should be `/get-started/install-cli/`.
- When you move or rename a page, add a redirect in `src/frontend/config/redirects.mjs`.

## Code example rules

- Indent fluent calls on new lines with 4 spaces. Do not align them under the first call.

  ```csharp
  builder.AddProject<Projects.Api>("api")
      .WithReference(redis)
      .WithExternalHttpEndpoints();
  ```

- Python uvicorn targets use `main:app`, not `main.app`.
- `process.env` is an object, not a method. `express` does not read environment variables.
- Connection string environment variables: C# reads `ConnectionStrings:<name>`
  (colon). Python and JavaScript read `ConnectionStrings__<name>` (double
  underscore). Use that pattern, not custom names such as `ELASTICSEARCH_ENDPOINT`.
- Never show `TrustServerCertificate=true` without saying it is for development only.

## Component rules

- Nested `Pivot` components must name their parent `PivotSelector` with `key`.
- Keep `LinkCard` descriptions short. Prefer "Configure persistence..." over
  "Discover how to configure persistence...".
- Do not place two `Aside` callouts that say similar things near each other.

## API references with `ApiReference`

- Use `<ApiReference />` only on the first named mention of an API in an article,
  and only when naming the API explains the behavior or the example.
- The limit is per API, per article, not per section or language tab.
- After the first mention, write "this method" or unlinked inline code.
- In bulleted or numbered API lists, repeat the component for every entry so the
  list stays consistent.
- An optional link in **See also** is allowed. Never add markup inside code fences.
- Match the reference to the API the example calls. A PostgreSQL example that calls
  `WithPostgresMcp()` links `Aspire.Hosting.PostgresBuilderExtensions.WithPostgresMcp`,
  not the generic `WithMcpServer`.

```mdx
import ApiReference from '@components/ApiReference.astro';

For PostgreSQL, use <ApiReference name="Aspire.Hosting.PostgresBuilderExtensions.WithPostgresMcp" /> to expose MCP tools for a database.
```

### Selecting an overload

- Author `name`, `package`, and `parameterTypes` as explicit static props. The
  authoring validator reports `unsupported-spread` when a spread could set any of them.
- By default the component shows the method name without `()` and links the method group.
- To pick one overload, set `parameterTypes` to the complete declared C# parameter
  types in order, copied from the generated C# catalog. Include the extension
  receiver's type, not the `this` keyword. Use `[]` only for a parameterless declaration.
- Do not copy C# parameter types into a TypeScript signature. A missing or
  ambiguous match is an authoring error, not permission to link the first overload.
- Use `package` when the same API is declared in more than one package.
- Do not add an authored `title` prop: the tooltip comes from the generated summary.
- Tooltips use the shared `src/frontend/src/scripts/tooltips.ts` lifecycle. Do not
  add a per-component initializer.

```mdx
<ApiReference
  name="Aspire.Hosting.ResourceBuilderExtensions.WithEnvironment"
  parameterTypes={[
    'Aspire.Hosting.ApplicationModel.IResourceBuilder<T>',
    'string',
    'string?',
  ]}
/>
```

## Packages and See also

- Reference NuGet packages with the package emoji and a link:
  `Install the [📦 Aspire.Hosting.Redis](https://nuget.org/packages/Aspire.Hosting.Redis) package.`
- End pages with **See also**: official technology docs, related Aspire docs,
  NuGet package pages, and GitHub repositories when they apply.

## Testing on aspire.dev

Before you submit, preview locally, check links, run code with `aspire run`,
confirm components render, confirm sidebar entries, and check integration logos
at desktop and mobile widths in light and dark themes.

Pick the smallest test set that proves the change:

| Change | Check |
|---|---|
| MDX copy, structure, navigation | Local preview and the edited links |
| Custom component usage | Component render tests |
| Component props | Prop-contract coverage |
| Interactive behavior | Targeted Playwright spec for that scenario |
| Accessibility-sensitive change | Rendered page plus focused accessibility tests |

Test layers that usually need an update when a custom component changes:

- `src/frontend/tests/unit/custom-components.vitest.test.ts` for render coverage.
- `src/frontend/tests/typecheck/component-props.contracts.ts` for typed props.
- `src/frontend/tests/e2e/*.spec.ts` for hydration, persistence, navigation, or accessibility.

```bash
bun run --cwd ./src/frontend test:unit:components
bun run --cwd ./src/frontend test:unit:contracts
bun run --cwd ./src/frontend playwright test tests/e2e/<relevant-spec>.spec.ts
```

Install the Aspire CLI only after the user confirms, from
<https://aspire.dev/get-started/install-cli/>. Never pipe a remote install script
to a shell without that confirmation.
Pick the channel that matches what you document:

| Channel | Use for | Installer option |
|---|---|---|
| Stable (default) | Released features | none |
| Dev | Unreleased features on `main` | `--quality dev` (Bash) or `-Quality 'dev'` (PowerShell) |
| Staging | Prereleases from the release branch | `--quality staging` or `-Quality 'staging'` |
| PR build | One unmerged PR in `microsoft/aspire` | Download the CLI from that PR's build artifacts |

Run the site with `aspire run`. It does not exit on its own, so an agent starts
it as a background process and stops it when testing ends. Add integration packages with `aspire add <package>`,
not `dotnet add package`. Find the `frontend` endpoint in the CLI output or the
dashboard, then use `playwright-cli open <frontend-url>`, `playwright-cli snapshot`,
and `playwright-cli click <ref>` instead of Playwright MCP tools.
