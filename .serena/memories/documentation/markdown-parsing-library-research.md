# Markdown Parsing Library Research Summary

**Date**: 2026-01-08
**Issue**: Replace fragile regex-based heading detection in SessionValidation.psm1

## Recommended Libraries

### Short-term (PowerShell)
**Markdig** (.NET) - BSD-2-Clause license
- Direct PowerShell integration via .NET interop
- Full AST with HeadingBlock objects
- Requires attribution in LICENSE file

### Long-term (TypeScript)
**remark/unified** - MIT license
- Industry standard for markdown tooling
- Excellent TypeScript types
- Fully compatible with MIT license

## License Compatibility
All recommended libraries are MIT-compatible:
- Markdig (BSD-2-Clause): Requires copyright notice attribution
- remark/unified (MIT): Identical license, no special handling needed

## Reference
Full analysis: `.agents/analysis/004-markdown-parsing-library-research.md`
