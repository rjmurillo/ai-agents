# Common Documentation Issues

These rules come from patterns reviewers flag again and again in documentation
pull requests. Check every draft and every audited page against them.

## Writing

- Drop commas that break a clause: write "Now that you have", not "Now, that you have".
- Keep casual asides out of documentation, such as "treat yourself to a coffee".
- Remove imports, includes, or components the page does not use.
- Every internal link must resolve to a page that exists today. Open the target.
- When you move or rename a page, add the redirect the site uses.

## Code examples

- Indent continuation lines with the language's standard indent, not by aligning
  them under the first call.
- Use one language identifier per fence, never a duplicate such as `csharp csharp`.
- Check names and syntax: module paths, package IDs, namespaces, and entry points.
- Describe APIs accurately. A property is not a method. Do not claim a library
  does something it does not do.
- Do not lead with a deprecated API. Show the current, recommended API first.
- Do not show an insecure default (disabled certificate checks, hard-coded
  secrets, permissive CORS) without saying it is for local development only.
- Define every variable before the example uses it. Do not delete a line that
  defines a variable a later example uses.

## Components and callouts

- Do not place two callouts that say similar things near each other.
- Keep card and link descriptions short enough that they do not crowd the layout.
- Match nested or paired components to the parent they belong to.

## Several languages or platforms on one page

- Show a complete, working example for each language or platform.
- Use the same resource names across every variant.
- When one variant is not supported yet, say so in one sentence. Do not invent a sample.
- Do not frame one platform as the default and the others as exceptions. Name
  the capability instead.

## Accuracy over plausibility

- Write only facts you verified in the code, the product, or a cited source.
- Pin versions, limits, and defaults to where you read them. Prefer the site's
  version placeholder when it has one, so the page does not go stale.
- If you cannot verify a claim, leave it out or mark the gap for the maintainer.
  Never fill a gap with a plausible guess.

## Links and cross-references

### Links to other pages

- Use the link form the site already uses: root-relative paths, relative file
  links, or a cross-reference syntax such as DocFX `xref`. Match the neighbors.
- Write link text that names the destination: "see [Configure retries](...)", not "click here".
- Link a concept on its first mention in a section where the reader may need it.
  Do not link every mention.

### Links to API reference

- Link an API on its first named mention in an article, and only when naming it
  helps explain the behavior or the example. Do not mention an API just to add a link.
- After the first mention, write "this method" or unlinked inline code.
- In a list of API entries, link every entry the same way so the list stays consistent.
- Never put link markup inside a code block. Code stays code.
- Link the API the example actually calls, and the exact overload when the page
  discusses one overload.

### Packages and external projects

- Link a package to its registry page (NuGet, npm, PyPI, crates.io) on first mention.
- Link the upstream project's own documentation for anything it owns. Do not
  restate its behavior from memory.

### See also

End a page with a short **See also** section when related pages exist: the
upstream technology's docs, related pages on this site, package pages, and the
source repository. Skip the section rather than padding it.
