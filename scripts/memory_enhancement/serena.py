"""Confidence scoring and citation management for Serena memories.

This module provides functions to manage citations in Serena memory files,
calculate confidence scores based on verification history, and update memory
frontmatter.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import frontmatter

from .citations import VerificationResult, verify_citation
from .models import Citation, Memory


def update_confidence(memory: Memory, verification: VerificationResult) -> None:
    """Update memory confidence score and last_verified timestamp.

    Writes updated confidence and last_verified fields to the memory's
    YAML frontmatter while preserving all other content and metadata.

    Args:
        memory: Memory instance to update
        verification: VerificationResult with confidence score

    Raises:
        FileNotFoundError: If memory file doesn't exist
        IOError: If file write fails
    """
    if not memory.path.exists():
        raise FileNotFoundError(f"Memory file not found: {memory.path}")

    # Read existing frontmatter and content
    with memory.path.open("r", encoding="utf-8") as f:
        post = frontmatter.load(f)

    # Update confidence and verification timestamp
    post.metadata["confidence"] = verification.confidence
    post.metadata["last_verified"] = datetime.now().isoformat()

    # Update citation validity in frontmatter
    if "citations" in post.metadata:
        citations_list = post.metadata["citations"]
        for i, citation_data in enumerate(citations_list):
            # Find matching citation in verification result
            citation_path = citation_data.get("path")
            citation_line = citation_data.get("line")

            # Update validity for stale citations
            for stale in verification.stale_citations:
                if stale.path == citation_path and stale.line == citation_line:
                    citation_data["valid"] = False
                    citation_data["mismatch_reason"] = stale.mismatch_reason
                    citation_data["verified"] = datetime.now().isoformat()
                    break
            else:
                # Citation is valid if not in stale list
                citation_data["valid"] = True
                citation_data["mismatch_reason"] = None
                citation_data["verified"] = datetime.now().isoformat()

    # Write updated frontmatter back to file
    with memory.path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))


def add_citation_to_memory(
    memory_path: Path,
    file_path: str,
    line: Optional[int] = None,
    snippet: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Add a citation to an existing Serena memory.

    Creates a Citation object, verifies it against the codebase, and appends
    it to the memory's YAML frontmatter. If the citation already exists
    (matching path and line), it will be updated instead of duplicated.

    Args:
        memory_path: Path to memory markdown file
        file_path: Relative path from repository root
        line: Line number (1-indexed), None for file-level citations
        snippet: Optional code snippet for fuzzy matching
        repo_root: Repository root (defaults to current directory)

    Raises:
        FileNotFoundError: If memory file or cited file doesn't exist
        ValueError: If citation is invalid (line out of bounds, etc.)
        IOError: If file write fails
    """
    if repo_root is None:
        repo_root = Path.cwd()

    if not memory_path.exists():
        raise FileNotFoundError(f"Memory file not found: {memory_path}")

    # Create and verify citation
    citation = Citation(path=file_path, line=line, snippet=snippet)
    verified_citation = verify_citation(citation, repo_root)

    if not verified_citation.valid:
        raise ValueError(
            f"Invalid citation: {verified_citation.mismatch_reason}"
        )

    # Read existing frontmatter
    with memory_path.open("r", encoding="utf-8") as f:
        post = frontmatter.load(f)

    # Initialize citations list if not present
    if "citations" not in post.metadata:
        post.metadata["citations"] = []

    citations_list = post.metadata["citations"]

    # Check for duplicate citation (same path and line)
    for i, existing in enumerate(citations_list):
        if existing.get("path") == file_path and existing.get("line") == line:
            # Update existing citation
            citations_list[i] = {
                "path": file_path,
                "line": line,
                "snippet": snippet,
                "verified": datetime.now().isoformat(),
                "valid": True,
                "mismatch_reason": None,
            }
            break
    else:
        # Add new citation
        citations_list.append({
            "path": file_path,
            "line": line,
            "snippet": snippet,
            "verified": datetime.now().isoformat(),
            "valid": True,
            "mismatch_reason": None,
        })

    # Recalculate confidence based on all citations
    valid_count = sum(1 for c in citations_list if c.get("valid", True))
    confidence = valid_count / len(citations_list) if citations_list else 1.0
    post.metadata["confidence"] = confidence
    post.metadata["last_verified"] = datetime.now().isoformat()

    # Write updated frontmatter back to file
    with memory_path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))


def get_confidence_history(memory: Memory) -> list[tuple[datetime, float]]:
    """Retrieve historical confidence scores from memory verification history.

    Note: Current implementation only returns the latest confidence score
    as historical tracking is not yet implemented. This is a placeholder
    for future enhancement.

    Args:
        memory: Memory instance

    Returns:
        List of (timestamp, confidence) tuples
    """
    if memory.last_verified and memory.confidence is not None:
        return [(memory.last_verified, memory.confidence)]
    return []


def list_citations_with_status(memory_path: Path, repo_root: Optional[Path] = None) -> list[dict]:
    """List all citations in a memory with their verification status.

    Args:
        memory_path: Path to memory markdown file
        repo_root: Repository root (defaults to current directory)

    Returns:
        List of dicts with citation data and current validity status

    Raises:
        FileNotFoundError: If memory file doesn't exist
    """
    if repo_root is None:
        repo_root = Path.cwd()

    if not memory_path.exists():
        raise FileNotFoundError(f"Memory file not found: {memory_path}")

    # Load memory
    memory = Memory.from_serena_file(memory_path)

    # Verify each citation and return status
    citations_status = []
    for citation in memory.citations:
        verified = verify_citation(citation, repo_root)
        citations_status.append({
            "path": verified.path,
            "line": verified.line,
            "snippet": verified.snippet,
            "valid": verified.valid,
            "mismatch_reason": verified.mismatch_reason,
            "verified": verified.verified.isoformat() if verified.verified else None,
        })

    return citations_status
