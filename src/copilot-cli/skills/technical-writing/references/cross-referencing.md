# Cross-Referencing

## Links to other pages

- Use the link form the site already uses: root-relative paths, relative file
  links, or a cross-reference syntax such as DocFX `xref`. Match the neighbors.
- Write link text that names the destination: `see [Configure retries](retries.md)`, not `click here`.
- Link a concept on its first mention in a section where the reader may need it.
  Do not link every mention.

## Links to API reference

- Link an API on its first named mention in an article, and only when naming it
  helps explain the behavior or the example. Do not mention an API just to add a link.
- After the first mention, write "this method" or unlinked inline code.
- In a list of API entries, link every entry the same way so the list stays consistent.
- Never put link markup inside a code block. Code stays code.
- Link the API the example actually calls, and the exact overload when the page
  discusses one overload.

## Packages and external projects

- Link a package to its registry page (NuGet, npm, PyPI, crates.io) on first mention.
- Link the upstream project's own documentation for anything it owns. Do not
  restate its behavior from memory.

## See also

End a page with a short **See also** section when related pages exist: the
upstream technology's docs, related pages on this site, package pages, and the
source repository. Skip the section rather than padding it.
