# PRD: Memory Enhancement Layer for Serena + Forgetful

**Status**: Draft
**Author**: Claude
**Created**: 2026-01-19
**Updated**: 2026-01-19
**Related Issues**: #724 (Traceability Graph), #584 (Serena Integration)
**Inspiration**: [GitHub Copilot Agentic Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)

---

## 1. Problem Statement

### 1.1 Current State

We have a working memory system:

| Component | Role | Status |
|-----------|------|--------|
| **Serena** | Canonical markdown storage (`.serena/memories/`) | ✅ 460+ memories |
| **Forgetful** | Semantic vector search | ✅ Configured |
| **MemoryRouter** | Unified search across both | ✅ ADR-037 |

### 1.2 What's Missing

GitHub Copilot's memory system revealed capabilities we lack:

| Capability | GitHub Copilot | Our System |
|------------|----------------|------------|
| **Citation validation** | Memories reference `file:line`, verified at retrieval | ❌ No citations |
| **Staleness detection** | Stale memories auto-flagged when code changes | ❌ Manual curation only |
| **Just-in-time verification** | Verify on read, not continuous sync | ❌ No verification |
| **Confidence scoring** | Track memory reliability over time | ❌ No scoring |
| **Graph traversal** | Navigate memory relationships | ⚠️ Links exist, no traversal tools |

### 1.3 Opportunity

**Enhance Serena + Forgetful** with citation validation and graph operations—don't replace them.

This delivers 90% of GitHub Copilot's value at 10% of the cost.

---

## 2. Goals and Non-Goals

### 2.1 Goals

| Priority | Goal | Success Metric |
|----------|------|----------------|
| P0 | **Citation schema for Serena memories** | Standardized frontmatter format |
| P0 | **Just-in-time citation verification** | `Verify-MemoryCitations.ps1` script |
| P1 | **Staleness detection in CI** | Pre-commit hook flags stale memories |
| P1 | **Graph traversal on Serena links** | Navigate memory relationships |
| P2 | **Confidence scoring** | Track verification history |
| P2 | **Multi-agent reinforcement** | Agents validate each other's memories |

### 2.2 Non-Goals

| Explicitly Out of Scope | Rationale |
|------------------------|-----------|
| Replace Serena | Already works, 460+ memories invested |
| Replace Forgetful | Already provides semantic search |
| New storage format | Serena markdown is fine |
| New MCP server | Adds complexity without benefit |
| Standalone operation without Serena | Not needed for this project |

### 2.3 Design Principle

> **Enhance, don't replace.** Every new capability should work WITH the existing Serena + Forgetful stack, not around it.

---

## 3. User Stories

### 3.1 Core Personas

| Persona | Description |
|---------|-------------|
| **Agent** | AI coding assistant using Serena for memory |
| **Developer** | Human who reviews/curates memories |
| **CI Pipeline** | Validates memory integrity on PR |

### 3.2 User Stories

#### US-1: Agent Saves Memory with Citations (P0)

**As an** agent that discovered a pattern,
**I want to** save it with references to specific code locations,
**So that** the memory can be validated against code changes.

**Acceptance Criteria:**
- [ ] Citation schema defined in Serena memory frontmatter
- [ ] `mcp__serena__write_memory` accepts citation metadata
- [ ] Citations include path, line number, and snippet

#### US-2: Agent Verifies Memory Before Acting (P0)

**As an** agent retrieving a memory,
**I want to** verify its citations still match the codebase,
**So that** I don't act on stale information.

**Acceptance Criteria:**
- [ ] Verification checks file:line exists
- [ ] Verification checks snippet content matches
- [ ] Stale citations return specific mismatch details
- [ ] Agent receives confidence score

#### US-3: CI Detects Stale Memories (P1)

**As a** CI pipeline,
**I want to** validate all memory citations on PR,
**So that** stale memories are flagged before merge.

**Acceptance Criteria:**
- [ ] Batch validation script for all Serena memories
- [ ] Exit code reflects validation status
- [ ] Report lists stale citations with details
- [ ] Integrates with existing pre-commit hooks

#### US-4: Agent Traverses Memory Graph (P1)

**As an** agent investigating a topic,
**I want to** follow links between related Serena memories,
**So that** I can build comprehensive understanding.

**Acceptance Criteria:**
- [ ] Graph traversal works on existing Serena link format
- [ ] Supports BFS/DFS with configurable depth
- [ ] Returns adjacency structure
- [ ] Uses `mcp__serena__*` tools, not custom storage

#### US-5: Developer Sees Memory Health Dashboard (P2)

**As a** developer,
**I want to** see which memories are stale or low-confidence,
**So that** I can prioritize curation efforts.

**Acceptance Criteria:**
- [ ] Script generates memory health report
- [ ] Shows last verified date per memory
- [ ] Ranks by staleness / confidence
- [ ] Outputs markdown for easy review

---

## 4. Technical Design

### 4.1 Citation Schema (Serena Memory Extension)

Extend existing Serena memory format with optional `citations` block:

```markdown
# .serena/memories/api-versioning.md (existing format)

This is the existing memory content...

## Citations

| File | Line | Snippet | Verified |
|------|------|---------|----------|
| src/client/constants.ts | 42 | `API_VERSION = 'v2'` | 2026-01-18 |
| server/routes/api.ts | 15 | `router.use('/v2'` | 2026-01-18 |

## Metadata

- **Confidence**: 0.92
- **Last Verified**: 2026-01-18T10:30:00Z
- **Links**: api-deployment-checklist, client-sdk-patterns
```

**Why table format?**
- Human-readable (grep/cat friendly)
- Parseable with simple regex
- No YAML frontmatter changes needed
- Backwards compatible with existing memories

### 4.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Enhancement Layer (NEW)                           │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐    │
│  │ Verify-Memory  │  │ Traverse-Graph │  │ Get-MemoryHealth   │    │
│  │ Citations.ps1  │  │ .ps1           │  │ Report.ps1         │    │
│  └───────┬────────┘  └───────┬────────┘  └─────────┬──────────┘    │
│          │                   │                      │               │
└──────────┼───────────────────┼──────────────────────┼───────────────┘
           │                   │                      │
           ▼                   ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Existing Stack (UNCHANGED)                        │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                    MemoryRouter.psm1                        │     │
│  │                    (ADR-037)                                │     │
│  └────────────────────────┬───────────────────────────────────┘     │
│                           │                                          │
│           ┌───────────────┴───────────────┐                         │
│           ▼                               ▼                         │
│  ┌─────────────────┐             ┌─────────────────┐                │
│  │ Serena MCP      │             │ Forgetful MCP   │                │
│  │ (Canonical)     │             │ (Semantic)      │                │
│  │ .serena/memories│             │ Vector search   │                │
│  └─────────────────┘             └─────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 Implementation

**Python-only implementation** for simplicity and cross-platform compatibility.

| Capability | Module |
|------------|--------|
| Citation verification | `citations.py` |
| Graph traversal | `graph.py` |
| Health reporting | `health.py` |
| Serena integration | `serena.py` |

**Why Python?**
- Better ecosystem for ML/embeddings (future Chroma integration)
- Claude Code tool calls work naturally with Python
- Cross-platform without runtime dependencies
- Zero external dependencies (stdlib only)

### 4.4 Package Structure

```
.claude/skills/memory-enhancement/
├── SKILL.md
├── src/
│   └── memory_enhancement/
│       ├── __init__.py
│       ├── citations.py      # Citation parsing & verification
│       ├── graph.py          # Graph traversal
│       ├── health.py         # Health reporting
│       ├── models.py         # Dataclasses
│       └── serena.py         # Serena MCP integration
└── tests/
    └── ...
```

#### 4.4.1 Core Models

```python
# src/memory_enhancement/models.py
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import re

@dataclass
class Citation:
    """Reference to a specific code location."""
    path: str
    line: Optional[int] = None
    snippet: Optional[str] = None
    verified: Optional[datetime] = None
    valid: Optional[bool] = None
    mismatch_reason: Optional[str] = None

@dataclass
class Memory:
    """Parsed Serena memory with citations."""
    id: str
    path: Path
    content: str
    citations: list[Citation] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    confidence: float = 0.5
    last_verified: Optional[datetime] = None

    @classmethod
    def from_serena_file(cls, path: Path) -> "Memory":
        """Parse a Serena memory markdown file."""
        content = path.read_text()
        memory_id = path.stem

        # Extract citations from ## Citations table
        citations = cls._parse_citations_table(content)

        # Extract links from ## Links section or [[wiki]] style
        links = cls._parse_links(content)

        # Extract confidence from ## Metadata
        confidence = cls._parse_confidence(content)

        return cls(
            id=memory_id,
            path=path,
            content=content,
            citations=citations,
            links=links,
            confidence=confidence
        )

    @staticmethod
    def _parse_citations_table(content: str) -> list[Citation]:
        """Parse markdown table in ## Citations section."""
        citations = []

        # Find ## Citations section
        match = re.search(
            r'## Citations\s*\n\|[^\n]+\|\s*\n\|[-\s|]+\|\s*\n((?:\|[^\n]+\|\s*\n?)+)',
            content
        )
        if not match:
            return citations

        # Parse table rows
        for row in match.group(1).strip().split('\n'):
            cells = [c.strip() for c in row.split('|')[1:-1]]
            if len(cells) >= 3:
                citations.append(Citation(
                    path=cells[0],
                    line=int(cells[1]) if cells[1].isdigit() else None,
                    snippet=cells[2].strip('`') if len(cells) > 2 else None,
                    verified=datetime.fromisoformat(cells[3]) if len(cells) > 3 and cells[3] else None
                ))

        return citations

    @staticmethod
    def _parse_links(content: str) -> list[str]:
        """Extract memory links from content."""
        links = []

        # Pattern 1: ## Links section with bullets
        match = re.search(r'## Links\s*\n((?:[-*]\s+.+\n?)+)', content)
        if match:
            links.extend(re.findall(r'[-*]\s+(\S+)', match.group(1)))

        # Pattern 2: [[wiki-style]] links
        links.extend(re.findall(r'\[\[([^\]]+)\]\]', content))

        return list(set(links))

    @staticmethod
    def _parse_confidence(content: str) -> float:
        """Extract confidence score from metadata."""
        match = re.search(r'\*\*Confidence\*\*:\s*([\d.]+)', content)
        return float(match.group(1)) if match else 0.5
```

#### 4.4.2 Citation Verification

```python
# src/memory_enhancement/citations.py
from pathlib import Path
from dataclasses import dataclass
from .models import Memory, Citation

@dataclass
class VerificationResult:
    memory_id: str
    valid: bool
    total_citations: int
    valid_count: int
    stale_citations: list[Citation]
    confidence: float

def verify_citation(citation: Citation, repo_root: Path) -> Citation:
    """
    Verify a single citation against the codebase.

    This is the GitHub Copilot insight: just-in-time verification
    at retrieval time, not continuous sync.
    """
    file_path = repo_root / citation.path

    # Check file exists
    if not file_path.exists():
        citation.valid = False
        citation.mismatch_reason = f"File not found: {citation.path}"
        return citation

    # If no line specified, file existence is enough
    if citation.line is None:
        citation.valid = True
        return citation

    # Check line exists and content matches
    lines = file_path.read_text().splitlines()

    if citation.line > len(lines):
        citation.valid = False
        citation.mismatch_reason = f"Line {citation.line} exceeds file length ({len(lines)})"
        return citation

    actual_line = lines[citation.line - 1]

    # Fuzzy match: snippet should be contained in line
    if citation.snippet and citation.snippet not in actual_line:
        citation.valid = False
        citation.mismatch_reason = f"Snippet mismatch. Expected '{citation.snippet}', got '{actual_line.strip()}'"
        return citation

    citation.valid = True
    return citation


def verify_memory(memory: Memory, repo_root: Path = None) -> VerificationResult:
    """Verify all citations in a memory."""
    repo_root = repo_root or Path.cwd()

    stale = []
    valid_count = 0

    for citation in memory.citations:
        verify_citation(citation, repo_root)
        if citation.valid:
            valid_count += 1
        else:
            stale.append(citation)

    # Calculate confidence based on citation validity
    if memory.citations:
        confidence = valid_count / len(memory.citations)
    else:
        confidence = memory.confidence  # No citations = use existing confidence

    return VerificationResult(
        memory_id=memory.id,
        valid=len(stale) == 0,
        total_citations=len(memory.citations),
        valid_count=valid_count,
        stale_citations=stale,
        confidence=confidence
    )


def verify_all_memories(memories_dir: Path, repo_root: Path = None) -> list[VerificationResult]:
    """Batch verify all memories in a directory."""
    repo_root = repo_root or Path.cwd()
    results = []

    for path in memories_dir.glob("*.md"):
        try:
            memory = Memory.from_serena_file(path)
            if memory.citations:  # Only verify memories with citations
                results.append(verify_memory(memory, repo_root))
        except Exception as e:
            print(f"Warning: Failed to parse {path}: {e}")

    return results
```

#### 4.4.3 Graph Traversal

```python
# src/memory_enhancement/graph.py
from pathlib import Path
from collections import deque
from dataclasses import dataclass
from .models import Memory

@dataclass
class GraphResult:
    """Result of graph traversal."""
    nodes: dict[str, list[str]]  # adjacency list
    visited_count: int
    max_depth_reached: int

def get_memory_links(memory_path: Path) -> list[str]:
    """Extract links from a memory file."""
    memory = Memory.from_serena_file(memory_path)
    return memory.links


def traverse_graph(
    root_id: str,
    memories_dir: Path,
    max_depth: int = 3,
    link_types: list[str] | None = None
) -> GraphResult:
    """
    BFS traversal of memory graph.

    Uses only file I/O on Serena memories - no external graph DB.
    """
    memories_dir = Path(memories_dir)
    visited = set()
    queue = deque([(root_id, 0)])
    graph = {}
    max_depth_reached = 0

    while queue:
        current_id, depth = queue.popleft()

        if current_id in visited or depth > max_depth:
            continue

        visited.add(current_id)
        max_depth_reached = max(max_depth_reached, depth)

        memory_path = memories_dir / f"{current_id}.md"

        if not memory_path.exists():
            continue

        links = get_memory_links(memory_path)
        graph[current_id] = links

        for link in links:
            if link not in visited:
                queue.append((link, depth + 1))

    return GraphResult(
        nodes=graph,
        visited_count=len(visited),
        max_depth_reached=max_depth_reached
    )


def find_related_memories(memory_id: str, memories_dir: Path) -> list[str]:
    """Find all memories that link TO this memory (reverse lookup)."""
    memories_dir = Path(memories_dir)
    related = []

    for path in memories_dir.glob("*.md"):
        if path.stem == memory_id:
            continue

        links = get_memory_links(path)
        if memory_id in links:
            related.append(path.stem)

    return related


def find_root_memories(memories_dir: Path) -> list[str]:
    """Find memories with no incoming links (graph roots)."""
    memories_dir = Path(memories_dir)

    # Collect all outgoing links
    all_targets = set()
    all_memories = set()

    for path in memories_dir.glob("*.md"):
        memory_id = path.stem
        all_memories.add(memory_id)
        links = get_memory_links(path)
        all_targets.update(links)

    # Roots are memories not targeted by any link
    return list(all_memories - all_targets)
```

#### 4.4.4 Serena Integration

```python
# src/memory_enhancement/serena.py
"""
Integration with Serena MCP for memory operations.

This module provides helpers to work with Serena memories
while the enhancement layer adds citation/graph capabilities.
"""
from pathlib import Path
from typing import Optional
from .models import Memory, Citation
from .citations import verify_memory, VerificationResult

# Default Serena memories location
SERENA_MEMORIES_DIR = Path(".serena/memories")


def search_with_verification(
    query: str,
    memories_dir: Path = SERENA_MEMORIES_DIR,
    verify: bool = False,
    min_confidence: float = 0.0
) -> list[tuple[Memory, Optional[VerificationResult]]]:
    """
    Search memories with optional citation verification.

    This wraps Serena's lexical search with our enhancement layer.
    For semantic search, use Forgetful MCP directly.
    """
    results = []
    query_terms = set(query.lower().split())

    for path in memories_dir.glob("*.md"):
        memory = Memory.from_serena_file(path)

        # Simple keyword match (Serena does this better via MCP)
        content_lower = memory.content.lower()
        if not any(term in content_lower for term in query_terms):
            continue

        verification = None
        if verify and memory.citations:
            verification = verify_memory(memory)
            if verification.confidence < min_confidence:
                continue

        results.append((memory, verification))

    return results


def add_citation_to_memory(
    memory_path: Path,
    file_path: str,
    line: Optional[int] = None,
    snippet: Optional[str] = None
) -> None:
    """
    Add a citation to an existing Serena memory.

    Appends to ## Citations table or creates it if missing.
    """
    from datetime import datetime

    content = memory_path.read_text()
    today = datetime.now().strftime("%Y-%m-%d")

    # Format citation row
    snippet_formatted = f"`{snippet}`" if snippet else ""
    new_row = f"| {file_path} | {line or ''} | {snippet_formatted} | {today} |"

    # Check if ## Citations section exists
    if "## Citations" in content:
        # Append to existing table
        lines = content.split("\n")
        for i, line_content in enumerate(lines):
            if line_content.startswith("## Citations"):
                # Find end of table (next ## or end of file)
                j = i + 1
                while j < len(lines) and not lines[j].startswith("##"):
                    j += 1
                # Insert before next section
                lines.insert(j, new_row)
                break
        content = "\n".join(lines)
    else:
        # Create new section before ## Links or at end
        citation_section = f"""
## Citations

| File | Line | Snippet | Verified |
|------|------|---------|----------|
{new_row}
"""
        if "## Links" in content:
            content = content.replace("## Links", f"{citation_section}\n## Links")
        else:
            content += citation_section

    memory_path.write_text(content)
```

#### 4.4.5 CLI Entry Point

```python
# src/memory_enhancement/__main__.py
"""CLI for memory enhancement tools."""
import argparse
import json
from pathlib import Path
from .citations import verify_memory, verify_all_memories
from .graph import traverse_graph, find_related_memories
from .health import generate_health_report
from .models import Memory

def main():
    parser = argparse.ArgumentParser(description="Memory Enhancement Tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify memory citations")
    verify_parser.add_argument("memory", help="Memory ID or path")
    verify_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # verify-all command
    verify_all_parser = subparsers.add_parser("verify-all", help="Verify all memories")
    verify_all_parser.add_argument("--dir", default=".serena/memories", help="Memories directory")
    verify_all_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # graph command
    graph_parser = subparsers.add_parser("graph", help="Traverse memory graph")
    graph_parser.add_argument("root", help="Root memory ID")
    graph_parser.add_argument("--depth", type=int, default=3, help="Max traversal depth")
    graph_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # related command
    related_parser = subparsers.add_parser("related", help="Find memories linking to target")
    related_parser.add_argument("memory", help="Target memory ID")

    # health command
    health_parser = subparsers.add_parser("health", help="Generate health report")
    health_parser.add_argument("--dir", default=".serena/memories", help="Memories directory")
    health_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")

    args = parser.parse_args()

    if args.command == "verify":
        path = Path(args.memory)
        if not path.exists():
            path = Path(".serena/memories") / f"{args.memory}.md"
        memory = Memory.from_serena_file(path)
        result = verify_memory(memory)

        if args.json:
            print(json.dumps({
                "memory_id": result.memory_id,
                "valid": result.valid,
                "confidence": result.confidence,
                "stale_citations": [
                    {"path": c.path, "line": c.line, "reason": c.mismatch_reason}
                    for c in result.stale_citations
                ]
            }, indent=2))
        else:
            status = "✅ VALID" if result.valid else "❌ STALE"
            print(f"{status} - {result.memory_id} (confidence: {result.confidence:.0%})")
            for c in result.stale_citations:
                print(f"  - {c.path}:{c.line} - {c.mismatch_reason}")

    elif args.command == "verify-all":
        results = verify_all_memories(Path(args.dir))
        if args.json:
            print(json.dumps([{
                "memory_id": r.memory_id,
                "valid": r.valid,
                "confidence": r.confidence
            } for r in results], indent=2))
        else:
            valid = sum(1 for r in results if r.valid)
            print(f"Verified {len(results)} memories: {valid} valid, {len(results) - valid} stale")
            for r in results:
                if not r.valid:
                    print(f"  ❌ {r.memory_id}")

    elif args.command == "graph":
        result = traverse_graph(args.root, Path(".serena/memories"), args.depth)
        if args.json:
            print(json.dumps({"nodes": result.nodes, "visited": result.visited_count}, indent=2))
        else:
            print(f"Graph from '{args.root}' (depth {result.max_depth_reached}):")
            for node, links in result.nodes.items():
                print(f"  {node} -> {', '.join(links) or '(no links)'}")

    elif args.command == "related":
        related = find_related_memories(args.memory, Path(".serena/memories"))
        print(f"Memories linking to '{args.memory}':")
        for r in related:
            print(f"  - {r}")

    elif args.command == "health":
        report = generate_health_report(Path(args.dir))
        print(report if args.format == "markdown" else json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
```

---

## 5. Integration Points

### 5.1 With Existing MemoryRouter (ADR-037)

The Python implementation can enhance the existing MemoryRouter by providing
citation verification as a post-search filter:

```python
# Example integration with MemoryRouter results
from memory_enhancement.citations import verify_memory
from memory_enhancement.models import Memory

def search_with_verification(serena_results: list, min_confidence: float = 0.5):
    """
    Filter Serena/Forgetful search results by citation validity.

    Called after MemoryRouter.Search-Memory returns results.
    """
    verified_results = []

    for result in serena_results:
        memory = Memory.from_serena_file(Path(result['Path']))

        if not memory.citations:
            # No citations = trust existing result
            verified_results.append(result)
            continue

        verification = verify_memory(memory)
        if verification.confidence >= min_confidence:
            result['confidence'] = verification.confidence
            result['citations_valid'] = verification.valid
            verified_results.append(result)

    return verified_results
```

### 5.2 With Session Protocol

Add to session start (optional gate):

```markdown
## Session Start (Enhanced)

1. ✅ Activate Serena
2. ✅ Read HANDOFF.md
3. ✅ Create session log
4. ✅ Read usage-mandatory memory
5. ✅ Verify branch
6. **NEW (optional)**: Run `python -m memory_enhancement health` for relevant memories
```

### 5.3 With CI/Pre-commit

```yaml
# .github/workflows/memory-validation.yml
name: Memory Validation

on:
  pull_request:
    paths:
      - '.serena/memories/**'
      - 'src/**'  # Code changes may invalidate citations

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Validate memory citations
        run: python -m memory_enhancement verify-all --json
        continue-on-error: true  # Warning, not blocking initially
```

---

## 6. Implementation Phases

### Phase 1: Citation Schema & Verification (1 week)

**Deliverables:**
- [ ] Document citation schema (table format in memory body)
- [ ] `models.py` - Memory and Citation dataclasses
- [ ] `citations.py` - single and batch verification
- [ ] Unit tests with pytest

**Exit Criteria:**
- Can verify citations in any Serena memory
- Clear pass/fail with details on mismatches
- `python -m memory_enhancement verify <memory>` works

### Phase 2: Graph Traversal (1 week)

**Deliverables:**
- [ ] `graph.py` - BFS/DFS traversal, related memories, root finding
- [ ] Integration with existing Serena link formats
- [ ] Cycle detection

**Exit Criteria:**
- Can traverse memory relationships
- Works with existing Serena memory format
- `python -m memory_enhancement graph <root>` works

### Phase 3: Health Reporting & CI Integration (1 week)

**Deliverables:**
- [ ] `health.py` - batch health check, markdown/JSON report generation
- [ ] CI workflow for PR validation (GitHub Actions)
- [ ] Pre-commit hook (optional)
- [ ] Documentation for adding citations to memories

**Exit Criteria:**
- CI flags stale memories on code changes
- Developers can see memory health at a glance
- `python -m memory_enhancement health` generates report

### Phase 4: Confidence Scoring & Tooling (1 week)

**Deliverables:**
- [ ] Confidence calculation based on verification history
- [ ] `serena.py` - helper to add citations to existing memories
- [ ] Integration with `reflect` skill for auto-citations
- [ ] Claude Code skill wrapper (`SKILL.md`)

**Exit Criteria:**
- Memories track confidence over time
- Easy to add/update citations via CLI or skill

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Citation coverage | 20% of high-value memories | Memories with ≥1 citation |
| Stale detection accuracy | >90% | True positives on known stale |
| CI integration | Active on all PRs | Workflow runs |
| Graph traversal performance | <500ms for depth 3 | Benchmark |
| Developer adoption | Citations added to new memories | PR reviews |

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Citation schema too complex | Medium | Medium | Use simple table format, not YAML |
| False positives (valid code flagged stale) | Medium | High | Fuzzy matching; snippet tolerance |
| Performance on large memory sets | Low | Medium | Lazy loading; caching |
| Adoption friction | Medium | Medium | Make citations optional; demonstrate value |
| Breaking existing memories | Low | High | Backwards compatible schema |

---

## 9. Open Questions

1. **Citation granularity**: File-level vs line-level vs function-level?
   - Recommendation: Line-level with fuzzy snippet matching

2. **Verification trigger**: On every read vs on-demand vs scheduled?
   - Recommendation: On-demand with CI batch validation

3. **Stale memory handling**: Warning vs blocking vs auto-archive?
   - Recommendation: Warning initially, blocking after adoption

4. **Serena schema extension**: Table in body vs YAML frontmatter?
   - Recommendation: Table in body (backwards compatible, human-readable)

---

## 10. Appendix

### A. Example Memory with Citations

```markdown
# API Version Synchronization

Client SDK API_VERSION constant must exactly match server route prefix.

## Why This Matters

Discovered during incident on 2026-01-10 when client was updated to v2
but server routes still used v1 prefix. All API calls returned 404.

## Action

When updating API version:
1. Search for `API_VERSION` in client code
2. Search for route prefix in server code
3. Update both in the same commit

## Citations

| File | Line | Snippet | Verified |
|------|------|---------|----------|
| src/client/constants.ts | 42 | `API_VERSION = 'v2'` | 2026-01-18 |
| server/routes/api.ts | 15 | `router.use('/v2'` | 2026-01-18 |

## Links

- api-deployment-checklist
- client-sdk-patterns

## Metadata

- **Confidence**: 0.92
- **Last Verified**: 2026-01-18T10:30:00Z
```

### B. Comparison: Enhancement vs Replacement

| Aspect | This PRD (Enhancement) | Original PRD (Replacement) |
|--------|------------------------|---------------------------|
| Storage | Serena (existing) | New markdown store |
| Semantic search | Forgetful (existing) | Chroma (new) |
| Effort | ~4 weeks | ~8 weeks |
| Risk | Low (additive) | High (migration) |
| Value delivered | Citations + Graph | Same |
| Dependencies | None new | chromadb, PyYAML |

### C. References

- [GitHub Copilot Agentic Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)
- [Issue #724: Traceability Graph Implementation](https://github.com/rjmurillo/ai-agents/issues/724)
- [ADR-007: Memory-First Architecture](/.agents/architecture/ADR-007-memory-first-architecture.md)
- [ADR-037: Memory Router Architecture](/.agents/architecture/ADR-037-memory-router-architecture.md)
- [Serena MCP Documentation](https://github.com/oraios/serena)
