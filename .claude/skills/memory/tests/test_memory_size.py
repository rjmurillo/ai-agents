"""Tests for test_memory_size.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from ..scripts.test_memory_size import MemorySizeValidator


@pytest.mark.parametrize(
    ("content", "expected_skills", "expected_categories"),
    [
        (
            """# Title

Body.

```bash
# alpha
# beta
# gamma
# delta
# epsilon
echo hi
```
""",
            0,
            1,
        ),
        (
            """# Title

## Real Skill

```r
## hidden skill comment
```
""",
            1,
            1,
        ),
        (
            """# Title

~~~bash
# hidden category
## hidden skill
~~~
## Real Skill
""",
            1,
            1,
        ),
        (
            """# Title

  ```python
# hidden category
## hidden skill
  ```
## Real Skill
""",
            1,
            1,
        ),
        (
            """# Title

````markdown
```bash
# hidden nested category
```
## hidden nested skill
````
## Real Skill
""",
            1,
            1,
        ),
    ],
)
def test_heading_counts_ignore_fenced_code_blocks(
    tmp_path: Path,
    content: str,
    expected_skills: int,
    expected_categories: int,
) -> None:
    target = tmp_path / "memory.md"
    target.write_text(content, encoding="utf-8")

    result = MemorySizeValidator().validate_file(target)

    assert result.is_valid is True
    assert result.skill_count == expected_skills
    assert result.category_count == expected_categories


def test_h2_category_fallback_ignores_fenced_code_blocks(tmp_path: Path) -> None:
    target = tmp_path / "memory.md"
    target.write_text(
        """## Git: Real Skill

```r
## R: Hidden fenced comment
```
""",
        encoding="utf-8",
    )

    result = MemorySizeValidator().validate_file(target)

    assert result.is_valid is True
    assert result.skill_count == 1
    assert result.category_count == 1
