# Markdown Parsing Library Research

**Issue**: Replace fragile regex-based heading detection in `scripts/modules/SessionValidation.psm1`
**Date**: 2026-01-08
**Status**: Research Complete

## Problem Statement

The current `Test-RequiredSections` function uses regex patterns like `'^##\s+Session\s+Start'` to match markdown headings. This approach is fragile because:

1. **Whitespace sensitivity**: Trailing spaces, tabs, or unusual whitespace breaks matches
2. **Heading variations**: ATX vs Setext headings, varying # counts
3. **Context blindness**: Cannot distinguish headings inside code blocks from real headings
4. **Maintenance burden**: Each new section requires new regex patterns

## Current Implementation (Fragile)

```powershell
# From Test-RequiredSections
$headingText = $section -replace '^##\s+', ''
$escapedText = [regex]::Escape($headingText)
$pattern = "^##+\s+$escapedText"
if ($SessionLogContent -notmatch "(?m)$pattern") {
    $missingSections += $section
}
```

## Research Findings

### PowerShell Options

#### Option 1: Markdig via .NET (RECOMMENDED for short-term)

**Library**: [Markdig](https://github.com/lunet-io/markdig) v0.37.0+
**Type**: .NET library (direct PowerShell interop)
**License**: BSD-2-Clause

**Pros**:

- Full AST access via `MarkdownDocument` object
- `HeadingBlock` type with `Level` (1-6) and `Inline` content
- Cross-platform (.NET Core/6+)
- Very fast (benchmarks show 10-20x faster than regex for complex docs)
- Already bundled with `MarkdownToHtml` PowerShell module

**Cons**:

- Requires loading .NET assembly
- Heavier than regex for simple cases

**Installation Options**:

```powershell
# Option A: Install MarkdownToHtml module (includes Markdig)
Install-Module -Name MarkdownToHtml -Scope CurrentUser

# Option B: Direct NuGet package
# Download from NuGet and load assembly
Add-Type -Path "path/to/Markdig.dll"
```

**Usage Example**:

```powershell
# Parse markdown and extract headings
Add-Type -Path "Markdig.dll"
$doc = [Markdig.Markdown]::Parse($markdownContent)
$headings = $doc | Where-Object { $_ -is [Markdig.Syntax.HeadingBlock] }
foreach ($h in $headings) {
    $level = $h.Level
    $text = $h.Inline | ForEach-Object { $_.ToString() } | Join-String
    Write-Output "H$level: $text"
}
```

#### Option 2: Node.js Bridge (markdown-it or remark)

**Approach**: Call Node.js script from PowerShell, parse JSON output
**Best Library**: `remark` (unified ecosystem)

**Pros**:

- Mature, well-maintained ecosystem
- Extensive plugin system
- GFM (GitHub Flavored Markdown) support built-in

**Cons**:

- Requires Node.js runtime
- Process spawning overhead
- JSON serialization/deserialization cost

**Usage Example**:

```powershell
# Create a small Node.js script: parse-headings.js
$nodeScript = @'
const {unified} = require('unified');
const remarkParse = require('remark-parse');
const {visit} = require('unist-util-visit');

const markdown = process.argv[2];
const tree = unified().use(remarkParse).parse(markdown);
const headings = [];
visit(tree, 'heading', (node) => {
  headings.push({
    level: node.depth,
    text: node.children.map(c => c.value || '').join('')
  });
});
console.log(JSON.stringify(headings));
'@

# Call from PowerShell
$result = node -e $nodeScript -- $markdownContent | ConvertFrom-Json
```

#### Option 3: pandoc JSON AST

**Tool**: [pandoc](https://pandoc.org/)
**Type**: External CLI tool

**Pros**:

- Most comprehensive markdown parser
- Outputs native JSON AST with `-t json`
- Handles every edge case

**Cons**:

- Heavy dependency (Haskell runtime)
- Not installed by default on any OS
- Overkill for heading extraction

**Usage Example**:

```powershell
$ast = $markdownContent | pandoc -f markdown -t json | ConvertFrom-Json
$headings = $ast.blocks | Where-Object { $_.t -eq 'Header' }
```

### TypeScript Options (Long-term Migration)

#### Option 1: unified/remark (RECOMMENDED)

**Packages**:

- `remark` (v15.0.1) - Main processor
- `remark-parse` (v11.0.0) - Markdown to AST
- `remark-gfm` (v4.0.1) - GitHub Flavored Markdown
- `@types/mdast` (v4.0.4) - TypeScript types

**Pros**:

- Industry standard for markdown tooling
- Excellent TypeScript support
- Modular plugin architecture
- Active maintenance (wooorm maintainer)
- Full GFM support including tables, task lists
- Extensive utility libraries (mdast-util-*)

**Example**:

```typescript
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import { visit } from 'unist-util-visit';
import type { Heading, Root } from 'mdast';

interface HeadingInfo {
  level: number;
  text: string;
  position: { line: number; column: number };
}

function extractHeadings(markdown: string): HeadingInfo[] {
  const tree = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .parse(markdown);

  const headings: HeadingInfo[] = [];
  
  visit(tree, 'heading', (node: Heading) => {
    const text = node.children
      .filter((c): c is { value: string } => 'value' in c)
      .map(c => c.value)
      .join('');
    
    headings.push({
      level: node.depth,
      text,
      position: {
        line: node.position?.start.line ?? 0,
        column: node.position?.start.column ?? 0
      }
    });
  });

  return headings;
}
```

#### Option 2: markdown-it

**Package**: `markdown-it` (v14.1.0)
**License**: MIT

**Pros**:

- Very fast parsing
- CommonMark compliant
- Zero dependencies for core
- Simpler API than remark

**Cons**:

- Designed for HTML output, AST is secondary
- Token stream rather than true AST
- Less TypeScript-native than remark

**Example**:

```typescript
import MarkdownIt from 'markdown-it';

const md = new MarkdownIt();
const tokens = md.parse(markdown, {});

const headings = tokens
  .filter(t => t.type === 'heading_open')
  .map((t, i) => ({
    level: parseInt(t.tag.slice(1), 10),
    text: tokens[tokens.indexOf(t) + 1]?.content ?? ''
  }));
```

#### Option 3: marked

**Package**: `marked` (v17.0.1)
**License**: MIT

**Pros**:

- Zero dependencies
- Very fast
- Simple API

**Cons**:

- Primarily for HTML rendering
- Lexer tokens, not AST
- Less suitable for structural analysis

**Not recommended** for AST-based validation.

## Comparison Matrix

| Criteria | Markdig (.NET) | remark (Node) | markdown-it | pandoc |
|----------|----------------|---------------|-------------|--------|
| **AST Quality** | Excellent | Excellent | Good | Excellent |
| **Cross-platform** | Yes | Yes | Yes | Yes |
| **Heading extraction** | Native | Native | Token-based | Native |
| **GFM tables** | Plugin | Plugin | Plugin | Built-in |
| **Performance** | Fast | Fast | Fastest | Slow |
| **Dependency weight** | Medium | Medium | Light | Heavy |
| **PowerShell integration** | Direct | Process spawn | Process spawn | Process spawn |
| **TypeScript support** | N/A | Excellent | Good | N/A |
| **Maintenance** | Active | Very active | Active | Active |

## License Compatibility (MIT Project)

This project uses the MIT license. All recommended libraries must be compatible.

### Compatibility Matrix

| Library | License | MIT Compatible? | Notes |
|---------|---------|-----------------|-------|
| **Markdig** | BSD-2-Clause | ✅ Yes | Permissive, requires attribution in docs |
| **remark/unified** | MIT | ✅ Yes | Identical license, fully compatible |
| **markdown-it** | MIT | ✅ Yes | Identical license, fully compatible |
| **marked** | MIT | ✅ Yes | Identical license, fully compatible |
| **pandoc** | GPL-2.0+ | ⚠️ Caution | CLI invocation fine; bundling problematic |

### License Details

**Markdig (BSD-2-Clause)**: Requires retaining copyright notice in source and binary distributions. No copyleft, no patent clauses. Safe for MIT projects with attribution.

**remark/unified (MIT)**: Identical license. No restrictions beyond attribution. Standard npm dependency management sufficient.

**pandoc (GPL-2.0+)**: CLI tool invocation (process spawning) is permissible. Bundling or linking to Haskell libraries would be problematic. Document already recommends against pandoc for other reasons.

### Attribution Requirements

If using Markdig, add to LICENSE or THIRD-PARTY-LICENSES file:

```text
Markdig
Copyright (c) Alexandre Mutel
BSD-2-Clause License
https://github.com/lunet-io/markdig
```

The remark ecosystem requires no special handling beyond normal npm dependency management (package.json).

## Recommendations

### Short-term: PowerShell (Markdig)

**Recommendation**: Use Markdig via .NET interop

**Rationale**:

1. Direct PowerShell integration (no process spawning)
2. Full AST with typed HeadingBlock objects
3. Already bundled with MarkdownToHtml module
4. Cross-platform support
5. No new runtime dependencies beyond .NET

**Implementation Path**:

1. Add Markdig.dll to `scripts/lib/` or use MarkdownToHtml module
2. Create `Get-MarkdownHeadings` function in SessionValidation.psm1
3. Replace regex patterns in `Test-RequiredSections` with AST queries
4. Add tests for edge cases (code blocks, setext headings)

**Estimated effort**: 4-8 hours

### Long-term: TypeScript Migration (remark)

**Recommendation**: Use unified/remark ecosystem

**Rationale**:

1. Industry standard for markdown tooling
2. Excellent TypeScript types via @types/mdast
3. Modular plugin architecture for future extensions
4. Same ecosystem used by many VS Code extensions
5. Can share validation logic between CI and editor

**Implementation Path**:

1. Create `packages/markdown-validator/` TypeScript package
2. Install: `npm install unified remark-parse remark-gfm @types/mdast unist-util-visit`
3. Implement heading extractor with full position information
4. Expose CLI for PowerShell to call during transition
5. Eventually replace PowerShell validation entirely

**Estimated effort**: 16-24 hours (includes tests, CLI wrapper)

## Migration Strategy

### Phase 1: Hardened PowerShell (2-4 weeks)

1. Add Markdig dependency
2. Implement `Get-MarkdownHeadings` using AST
3. Refactor `Test-RequiredSections` to use new function
4. Add comprehensive tests for edge cases
5. Keep regex as fallback if assembly load fails

### Phase 2: TypeScript Foundation (4-8 weeks)

1. Create TypeScript package with remark
2. Implement session log validator in TypeScript
3. Create CLI entry point
4. Update CI to use TypeScript validator
5. PowerShell calls TypeScript CLI

### Phase 3: Full TypeScript Migration (8-12 weeks)

1. Port remaining validation logic to TypeScript
2. Integrate with VS Code extension (if applicable)
3. Deprecate PowerShell validation module
4. Remove regex fallbacks

## Appendix: Package Details

### remark Ecosystem Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `unified` | 11.0.0 | Core processor |
| `remark-parse` | 11.0.0 | Markdown parser |
| `remark-gfm` | 4.0.1 | GFM extension |
| `remark-stringify` | 11.0.0 | AST to markdown |
| `@types/mdast` | 4.0.4 | TypeScript types |
| `unist-util-visit` | 5.0.0 | Tree traversal |
| `mdast-util-toc` | 7.1.0 | TOC extraction |
| `mdast-util-heading-range` | 4.0.0 | Section extraction |

### Markdig Features

- CommonMark 0.31 compliant
- Extensions: GFM, tables, task lists, footnotes, math, diagrams
- Syntax highlighting integration
- Custom renderer support
- Position tracking for error reporting
