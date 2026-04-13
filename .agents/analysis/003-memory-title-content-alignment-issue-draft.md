# GitHub Issue Draft: AI-Assisted Memory Title/Content Alignment Validation

## Title
Add AI-Assisted Memory Title/Content Alignment Validation to CI

## Labels
- `enhancement`
- `validation`
- `memory`
- `ci`
- `P1`

## Milestone
TBD (suggest: next sprint)

## Issue Body

### Summary

Memory files can drift from their titles, creating discoverability gaps in the lexical matching system. This issue proposes adding automated alignment validation using embedding similarity.

### Problem

**Tiered memory architecture (ADR-017) relies on keyword-based discovery**. When file names do not accurately reflect content, LLM agents cannot find relevant skills.

**Observed Examples**:

| File Name | Actual Content | Issue |
|-----------|---------------|-------|
| `bash-integration-exit-code-testing.md` | PowerShell `$LASTEXITCODE` testing | Searching "PowerShell exit code" misses this file |
| `bash-integration-exit-codes.md` | PowerShell script scope semantics | Cross-domain keyword gap |

**Impact**:
- Agents load wrong files (wasted tokens)
- Retrieval precision degrades
- Keyword density validation (ADR-017 P0) undermined

**Scale**: 439 memory files, 74 mention PowerShell, 36 domain indices affected.

### Proposed Solution

**Option B (Recommended)**: CI workflow with embedding similarity validation

**Architecture**:

```yaml
# .github/workflows/memory-alignment-audit.yml
name: Memory Title Alignment Audit

on:
  pull_request:
    paths: ['.serena/memories/**']

jobs:
  embedding-similarity:
    runs-on: ubuntu-24.04-arm  # ADR-014: cost optimization
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install sentence-transformers scikit-learn

      - name: Validate Memory Alignment
        run: python scripts/validate-memory-alignment.py

      - name: Report Findings
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const results = require('./alignment-results.json');
            // Post PR comment with flagged files
```

**Validation Logic** (`scripts/validate-memory-alignment.py`):

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path
import json

model = SentenceTransformer('all-MiniLM-L6-v2')  # Fast, local model (no API cost)

def compute_similarity(filename, content):
    """
    Compute cosine similarity between filename and content embeddings.
    Threshold: 0.7 (files below this are flagged for review)
    """
    filename_emb = model.encode([filename])
    content_emb = model.encode([content[:500]])  # First 500 chars
    return cosine_similarity(filename_emb, content_emb)[0][0]

def audit_memory_files(memory_dir):
    results = []
    for filepath in Path(memory_dir).glob('*.md'):
        filename = filepath.stem
        content = filepath.read_text(encoding='utf-8')
        score = compute_similarity(filename, content)

        status = 'PASS' if score >= 0.7 else 'WARN'
        results.append({
            'file': filename,
            'score': round(score, 3),
            'status': status
        })

    return results

if __name__ == '__main__':
    results = audit_memory_files('.serena/memories')

    # Write results to JSON for GitHub Actions consumption
    with open('alignment-results.json', 'w') as f:
        json.dump(results, f, indent=2)

    # Print summary
    warnings = [r for r in results if r['status'] == 'WARN']
    print(f"Total files: {len(results)}")
    print(f"Warnings: {len(warnings)}")

    if warnings:
        print("\nFlagged files (score <0.7):")
        for w in warnings:
            print(f"  - {w['file']}: {w['score']}")
```

**Output Format** (PR Comment):

```markdown
## Memory Title Alignment Audit

**Status**: 3 files flagged for review

| File | Similarity Score | Status |
|------|-----------------|--------|
| bash-integration-exit-code-testing | 0.62 | ⚠️ WARN |
| bash-integration-exit-codes | 0.58 | ⚠️ WARN |
| copilot-platform-priority | 0.85 | ✅ PASS |

### Recommendations

**bash-integration-exit-code-testing.md**:
- Add keywords: `PowerShell`, `LASTEXITCODE`, `Pester`
- Consider: Update index entry to `bash-integration PowerShell exit-code LASTEXITCODE testing`

**bash-integration-exit-codes.md**:
- Add keywords: `PowerShell`, `script-scope`, `return`, `exit`
- Consider: Rename to `bash-integration-powershell-exit-codes.md` or update keywords
```

### Cost Analysis

| Approach | Cost/Month | Latency | Precision |
|----------|-----------|---------|-----------|
| **Embedding (CI)** | $0 (local model) | 30s/PR | Medium |
| LLM (CI) | $4 | Non-blocking | High |
| Deterministic | $0 | <1s | Low |

**Recommendation**: Use local Sentence Transformers model (no API cost).

### Implementation Checklist

**Phase 1: Core Validation**
- [ ] Create `scripts/validate-memory-alignment.py`
- [ ] Add `.github/workflows/memory-alignment-audit.yml`
- [ ] Test on sample PRs
- [ ] Document in `.agents/architecture/` (ADR or update ADR-017)

**Phase 2: Validation Integration**
- [ ] Extend `Validate-MemoryIndex.ps1` with P2 cross-domain keyword check
- [ ] Add validation to pre-commit hook (optional, non-blocking)

**Phase 3: Enhanced Reporting**
- [ ] LLM-powered keyword suggestions (for flagged files only)
- [ ] Batch monthly audit for comprehensive review

### Success Criteria

- [ ] CI workflow detects title/content drift on PRs modifying `.serena/memories/`
- [ ] Flagged files reported as PR comment (non-blocking warning)
- [ ] Zero recurring API costs (local model)
- [ ] Workflow completes in <60 seconds
- [ ] False positive rate <10% (validated on sample files)

### Related

- **Analysis**: `.agents/analysis/003-memory-title-content-alignment-detection.md`
- **ADR-017**: Tiered Memory Index Architecture
- **Validation**: `scripts/Validate-MemoryIndex.ps1`
- **AI PR Quality Gate**: `.github/workflows/ai-pr-quality-gate.yml` (pattern to follow)

### References

- [Sentence Transformers - Semantic Similarity](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)
- [Google Magika - AI File Content Detection](https://github.com/google/magika)
- [Hugging Face - Sentence Similarity](https://huggingface.co/tasks/sentence-similarity)

---

**Priority**: P1 (directly impacts ADR-017 keyword density validation effectiveness)
**Effort**: M (1-2 days)
**Risk**: Low (non-blocking validation, no external API dependency)
