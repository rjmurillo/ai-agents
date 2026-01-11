# Plan: Fix All PR #760 Review Issues

## Overview

PR #760 has 30+ issues identified by code-reviewer, comment-analyzer, and silent-failure-hunter agents, plus 4 CodeQL security alerts. This plan addresses all issues using a conservative fix approach that modifies existing files without changing the fundamental skill validation architecture.

The key insight is that `validate-skill.py` (full development validation) and `quick_validate.py` (minimal packaging validation) serve intentionally different purposes. Rather than unifying them, we document the difference and fix the actual defects: silent failures, path injection vulnerabilities, missing skip mechanism, and outdated documentation.

## Planning Context

### Decision Log

| Decision | Reasoning Chain |
|----------|-----------------|
| Add `is_safe_path()` validation | CodeQL identifies path injection at 4 locations -> user-provided paths could escape intended directories -> resolve paths and verify they stay within expected boundaries -> prevents directory traversal attacks |
| Log errors to stderr instead of silently returning None | Silent failures hide problems from users and debugging -> logging to stderr preserves stdout for structured output -> explicit error messages enable troubleshooting without breaking existing integrations |
| Use SKIP_SKILL_VALIDATION environment variable | Pre-commit hooks need documented skip mechanism for CI/emergencies -> env var pattern already used by other hooks -> explicit opt-in prevents accidental misuse -> matches convention for SKIP_* variables |
| Keep validate-skill.py and quick_validate.py separate | quick_validate.py docstring states "minimal validation for packaging" -> full validation includes dev-time checks (Process, Verification sections) not needed for distribution -> merging would conflate distinct purposes |
| Triggers section is RECOMMENDED not ERROR | skill-description-trigger-standard.md v2.0 line 303 says "BREAKING: Changed triggers section from REQUIRED to RECOMMENDED" -> validator should warn not error -> aligns Anthropic spec: description is primary trigger |
| Use specific exception types | Broad `except Exception` catches too much -> specific types (FileNotFoundError, json.JSONDecodeError, etc.) enable targeted handling -> improves debuggability without hiding unexpected errors |

### Rejected Alternatives

| Alternative | Why Rejected |
|-------------|--------------|
| Unify validators into single script | quick_validate.py intentionally minimal for packaging per its docstring. Full validation includes development-time sections not needed for distribution. Merging conflates distinct purposes. |
| Strict mode requiring full validation everywhere | Would break existing skills that pass quick_validate but not full validation. Migration burden exceeds value for this PR. |
| Remove triggers section validation entirely | Triggers still valuable for discoverability. RECOMMENDED (warn) balances guidance vs enforcement. |

### Constraints and Assumptions

- Python 3.8+ compatibility required (match existing scripts)
- No new dependencies (resolve() and Path operations are stdlib)
- Pre-commit hook must remain bash (not PowerShell despite ADR-005, this is for developer machines)
- CodeQL rules require specific path validation patterns for py/path-injection

### Known Risks

| Risk | Mitigation | Anchor |
|------|------------|--------|
| Path validation breaks legitimate paths | Only validate paths stay within cwd or home directory, not arbitrary restrictions | fix_fences.py:113 `if not directory.exists()` already validates existence |
| Error logging changes script output format | Log to stderr not stdout, preserving JSON/structured output on stdout | discover_skills.py:390 `print(json.dumps(result.to_dict(), indent=2))` uses stdout |
| Skip mechanism abused to bypass validation | Requires explicit SKIP_SKILL_VALIDATION=1, documented as emergency use only | N/A - new code, no anchor needed |

## Invisible Knowledge

### Architecture

```
+------------------+     +-------------------+
| validate-skill.py|     | quick_validate.py |
| (full dev-time)  |     | (minimal package) |
| - frontmatter    |     | - frontmatter     |
| - triggers       |     | - name/desc only  |
| - process        |     +-------------------+
| - verification   |              |
| - anti-patterns  |              v
+------------------+     +-------------------+
         |               | package_skill.py  |
         v               | (uses quick_)     |
+------------------+     +-------------------+
| pre-commit hook  |
| (uses quick_)    |
+------------------+
```

### Data Flow

```
Skill File (SKILL.md)
        |
        v
Parse YAML Frontmatter
        |
        +---> validate-skill.py path: Full structural validation
        |     (triggers, process, verification, anti-patterns, scripts)
        |
        +---> quick_validate.py path: Minimal packaging validation
              (name format, description length, allowed properties)
```

### Why This Structure

Two validators exist because:

1. **Development-time validation** (validate-skill.py) helps authors create high-quality skills with complete documentation
2. **Packaging validation** (quick_validate.py) ensures only essential properties for distribution, per Anthropic Claude Code spec

Merging them would either make packaging too strict (rejecting valid packages) or development too lax (missing quality signals).

### Invariants

- Scripts MUST log errors to stderr, never silently return None
- Path operations MUST resolve and validate paths before file operations
- Pre-commit validation MUST be skippable for emergencies
- Documentation MUST match actual validator behavior

## Milestones

### Milestone 1: CodeQL Path Injection Fixes (BLOCKING)

**Files**:
- `.claude/skills/fix-markdown-fences/fix_fences.py`
- `.claude/skills/metrics/collect_metrics.py`

**Flags**: needs error handling review (first use of is_safe_path pattern)

**Requirements**:
- Add `is_safe_path()` function that validates paths stay within allowed directories
- Use resolved paths before any file operations
- Log warning and skip unsafe paths rather than raising exceptions

**Acceptance Criteria**:
- CodeQL scan passes (no py/path-injection alerts)
- Scripts still function for legitimate paths within cwd and home

**Code Changes**:

```diff
--- a/.claude/skills/fix-markdown-fences/fix_fences.py
+++ b/.claude/skills/fix-markdown-fences/fix_fences.py
@@ -7,6 +7,22 @@ import re
 import sys
 from pathlib import Path

+def is_safe_path(path: Path, allowed_roots: list[Path]) -> bool:
+    """Validate path stays within allowed directories.
+
+    Prevents path traversal attacks by ensuring resolved path
+    is under one of the allowed root directories.
+    """
+    try:
+        resolved = path.resolve()
+        return any(
+            resolved == root or root in resolved.parents
+            for root in allowed_roots
+        )
+    except (OSError, ValueError):
+        return False
+

 def fix_markdown_fences(content: str) -> str:
```

```diff
--- a/.claude/skills/fix-markdown-fences/fix_fences.py
+++ b/.claude/skills/fix-markdown-fences/fix_fences.py
@@ -69,9 +85,17 @@ def main() -> int:
     args = parser.parse_args()

+    # Define allowed roots for path validation
+    allowed_roots = [Path.cwd().resolve(), Path.home().resolve()]
+
     total_fixed = 0
     for dir_path in args.directories:
         directory = Path(dir_path)
+        # Validate path before operations
+        if not is_safe_path(directory, allowed_roots):
+            print(f"Warning: {dir_path} is outside allowed directories", file=sys.stderr)
+            continue
         if not directory.exists():
             print(f"Warning: {dir_path} does not exist", file=sys.stderr)
             continue
```

```diff
--- a/.claude/skills/metrics/collect_metrics.py
+++ b/.claude/skills/metrics/collect_metrics.py
@@ -420,9 +420,23 @@ def main():

     args = parser.parse_args()

+    def is_safe_path(path: Path, allowed_roots: list) -> bool:
+        """Validate path stays within allowed directories."""
+        try:
+            resolved = path.resolve()
+            return any(
+                resolved == root or root in resolved.parents
+                for root in allowed_roots
+            )
+        except (OSError, ValueError):
+            return False
+
     # Validate repo path
     repo_path = Path(args.repo).resolve()
+    allowed_roots = [Path.cwd().resolve(), Path.home().resolve()]
+    if not is_safe_path(repo_path, allowed_roots):
+        print(f"Error: {args.repo} is outside allowed directories", file=sys.stderr)
+        sys.exit(1)
     if not (repo_path / ".git").exists():
         print(f"Error: {repo_path} is not a git repository", file=sys.stderr)
         sys.exit(1)
```

---

### Milestone 2: Silent Failure Fixes (CRITICAL)

**Files**:
- `.claude/skills/SkillForge/scripts/discover_skills.py`
- `.claude/skills/SkillForge/scripts/triage_skill_request.py`
- `.claude/skills/SkillForge/scripts/quick_validate.py`
- `.claude/skills/SkillForge/scripts/package_skill.py`
- `.claude/skills/SkillForge/scripts/validate-skill.py`

**Flags**: needs error handling review

**Requirements**:
- Replace silent `return None` with logged error message + return
- Use specific exception types (FileNotFoundError, json.JSONDecodeError, etc.)
- Add error details to Result objects where applicable
- Add index structure validation in triage_skill_request.py

**Acceptance Criteria**:
- All file read errors produce stderr output
- All JSON decode errors produce stderr output with path
- All zip creation errors produce stderr output
- Script exit codes remain correct (0=success, 1=failure)

**Code Changes**:

```diff
--- a/.claude/skills/SkillForge/scripts/discover_skills.py
+++ b/.claude/skills/SkillForge/scripts/discover_skills.py
@@ -220,8 +220,12 @@ def parse_skill_file(path: Path, source_name: str, priority: int) -> Optional[Di
     """Parse a skill file and extract metadata."""
     try:
         content = path.read_text(encoding="utf-8")
-    except Exception as e:
+    except FileNotFoundError:
+        print(f"Warning: Skill file not found: {path}", file=sys.stderr)
+        return None
+    except (OSError, UnicodeDecodeError) as e:
+        print(f"Warning: Failed to read {path}: {e}", file=sys.stderr)
         return None
```

```diff
--- a/.claude/skills/SkillForge/scripts/discover_skills.py
+++ b/.claude/skills/SkillForge/scripts/discover_skills.py
@@ -335,7 +339,12 @@ def save_index(result: Result, output_path: Optional[Path] = None) -> None:
         "total_count": result.data["total_count"]
     }

-    path.write_text(json.dumps(index_data, indent=2))
+    try:
+        path.write_text(json.dumps(index_data, indent=2))
+    except OSError as e:
+        print(f"Error: Failed to save index to {path}: {e}", file=sys.stderr)
+        raise
```

```diff
--- a/.claude/skills/SkillForge/scripts/discover_skills.py
+++ b/.claude/skills/SkillForge/scripts/discover_skills.py
@@ -167,7 +167,11 @@ def extract_triggers(content: str) -> List[str]:

     # Also extract from trigger tables
     table_pattern = r'\|\s*`([^`]+)`\s*\|'
-    if "Trigger" in content:
+    # Case-insensitive search for Trigger section
+    trigger_start = content.lower().find("trigger")
+    if trigger_start != -1:
+        # Find section end (next --- or end of content)
+        section_end = content.find("---", trigger_start)
+        table_section = content[trigger_start:section_end if section_end != -1 else len(content)]
-        table_section = content[content.find("Trigger"):content.find("---", content.find("Trigger"))]
         matches = re.findall(table_pattern, table_section)
         triggers.extend(matches)
```

```diff
--- a/.claude/skills/SkillForge/scripts/triage_skill_request.py
+++ b/.claude/skills/SkillForge/scripts/triage_skill_request.py
@@ -216,9 +216,15 @@ def load_skill_index() -> Optional[Dict]:
     if not index_path.exists():
         return None
     try:
-        return json.loads(index_path.read_text())
+        content = index_path.read_text()
     except json.JSONDecodeError:
+        print(f"Error: Invalid JSON in skill index: {index_path}", file=sys.stderr)
+        return None
+    except OSError as e:
+        print(f"Error: Failed to read skill index: {e}", file=sys.stderr)
         return None
+
+    try:
+        data = json.loads(content)
+    except json.JSONDecodeError as e:
+        print(f"Error: Invalid JSON in skill index {index_path}: {e}", file=sys.stderr)
+        return None
+
+    # Validate index structure
+    if not isinstance(data, dict):
+        print(f"Error: Skill index must be a dictionary, got {type(data).__name__}", file=sys.stderr)
+        return None
+    if "skills" not in data:
+        print(f"Error: Skill index missing 'skills' key", file=sys.stderr)
+        return None
+
+    return data
```

```diff
--- a/.claude/skills/SkillForge/scripts/quick_validate.py
+++ b/.claude/skills/SkillForge/scripts/quick_validate.py
@@ -45,7 +45,14 @@ def validate_skill(skill_path):
     if not skill_md.exists():
         return False, "SKILL.md not found"

-    # Read and validate frontmatter
-    content = skill_md.read_text()
+    # Read skill file with explicit error handling
+    try:
+        content = skill_md.read_text(encoding="utf-8")
+    except FileNotFoundError:
+        return False, f"SKILL.md not found at {skill_md}"
+    except (OSError, UnicodeDecodeError) as e:
+        return False, f"Failed to read SKILL.md: {e}"
+
+    # Validate frontmatter
     if not content.startswith('---'):
         return False, "No YAML frontmatter found"
```

```diff
--- a/.claude/skills/SkillForge/scripts/package_skill.py
+++ b/.claude/skills/SkillForge/scripts/package_skill.py
@@ -77,7 +77,7 @@ def package_skill(skill_path, output_dir=None):
     # Create the .skill file (zip format)
     try:
         with zipfile.ZipFile(skill_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
-            # Walk through the skill directory
+            # Walk through the skill directory and add files
             for file_path in skill_path.rglob('*'):
                 if file_path.is_file():
                     # Skip common exclusions
@@ -85,14 +85,22 @@ def package_skill(skill_path, output_dir=None):
                         continue
                     # Calculate the relative path within the zip
                     arcname = file_path.relative_to(skill_path.parent)
-                    zipf.write(file_path, arcname)
+                    try:
+                        zipf.write(file_path, arcname)
+                    except (OSError, zipfile.BadZipFile) as e:
+                        print(f"  Warning: Failed to add {file_path}: {e}", file=sys.stderr)
+                        continue
                     print(f"  Added: {arcname}")

         print(f"\n[OK] Successfully packaged skill to: {skill_filename}")
         return skill_filename

-    except Exception as e:
-        print(f"[FAIL] Error creating .skill file: {e}")
+    except zipfile.BadZipFile as e:
+        print(f"[FAIL] Invalid zip file format: {e}", file=sys.stderr)
+        return None
+    except OSError as e:
+        print(f"[FAIL] File system error creating .skill file: {e}", file=sys.stderr)
         return None
```

```diff
--- a/.claude/skills/SkillForge/scripts/validate-skill.py
+++ b/.claude/skills/SkillForge/scripts/validate-skill.py
@@ -44,10 +44,14 @@ class SkillValidator:
             return False

         try:
-            self.content = self.skill_md_path.read_text(encoding="utf-8")
+            self.content = self.skill_md_path.read_text(encoding='utf-8')
             return True
-        except Exception as e:
+        except FileNotFoundError:
+            self.errors.append(f"Skill file not found: {self.skill_md_path}")
+            return False
+        except (OSError, UnicodeDecodeError) as e:
             self.errors.append(f"Failed to read skill file: {e}")
             return False

@@ -58,11 +62,14 @@ class SkillValidator:
             return False

         try:
             import yaml
             self.frontmatter = yaml.safe_load(match.group(1))
             return True
         except ImportError:
             # Parse basic fields without yaml library
-            frontmatter_text = match.group(1)
+            self._parse_frontmatter_fallback(match.group(1))
+            return True
+        except yaml.YAMLError as e:
+            self.errors.append(f"Invalid YAML in frontmatter: {e}")
+            return False
-        except Exception as e:
-            self.errors.append(f"Failed to parse frontmatter: {e}")
-            return False
```

```diff
--- a/.claude/skills/SkillForge/scripts/validate-skill.py
+++ b/.claude/skills/SkillForge/scripts/validate-skill.py
@@ -295,10 +303,14 @@ class SkillValidator:
     def _validate_script(self, script_path: Path):
         """Validate a single Python script file."""
         try:
-            content = script_path.read_text(encoding="utf-8")
-        except Exception as e:
+            content = script_path.read_text(encoding='utf-8')
+        except FileNotFoundError:
+            self.check(
+                f"script.{script_path.name}.readable",
+                False,
+                f"Script file not found: {script_path.name}"
+            )
+            return
+        except (OSError, UnicodeDecodeError) as e:
             self.check(
                 f"script.{script_path.name}.readable",
                 False,
                 f"Cannot read script {script_path.name}: {e}"
             )
             return
```

---

### Milestone 3: Pre-commit Hook Improvements (IMPORTANT)

**Files**:
- `.githooks/pre-commit`

**Flags**: needs conformance check (first use of SKIP_SKILL_VALIDATION pattern)

**Requirements**:
- Add SKIP_SKILL_VALIDATION environment variable check
- Improve exit code capture from validator
- Add documentation comment explaining skip mechanism

**Acceptance Criteria**:
- Setting SKIP_SKILL_VALIDATION=1 skips skill validation with warning
- Exit code from validator is properly captured
- Skip mechanism is documented in hook comments

**Code Changes**:

```diff
--- a/.githooks/pre-commit
+++ b/.githooks/pre-commit
@@ -559,6 +559,17 @@ if [ -n "$STAGED_SKILL_FILES" ]; then
     echo_info "Validating staged skill files..."

+    # Skip mechanism for emergencies or CI
+    # Usage: SKIP_SKILL_VALIDATION=1 git commit -m "message"
+    # WARNING: Only use in emergencies. Skipping validation may allow invalid skills.
+    if [ "${SKIP_SKILL_VALIDATION:-0}" = "1" ]; then
+        echo_warning "SKIP_SKILL_VALIDATION is set. Skipping skill validation."
+        echo_warning "This should only be used in emergencies."
+    else
+
     # MEDIUM-002: Reject symlinks for security
     if [ -L "$SKILL_VALIDATOR" ]; then
         echo_error "Skill validator path is a symlink (security violation)"
         EXIT_STATUS=1
-    elif [ -f "$SKILL_VALIDATOR" ]; then
+    elif [ ! -f "$SKILL_VALIDATOR" ]; then
+        echo_error "Skill validator not found: $SKILL_VALIDATOR"
+        EXIT_STATUS=1
+    else
         if command -v python3 &> /dev/null; then
             # Validate each staged SKILL.md file
             VALIDATION_FAILED=0
             while IFS= read -r skill_md; do
                 [ -z "$skill_md" ] && continue

                 # Get the skill directory (parent of SKILL.md)
                 skill_dir=$(dirname "$skill_md")

                 # Run validator on the skill directory
-                if python3 "$SKILL_VALIDATOR" "$skill_dir" 2>&1; then
+                validator_output=$(python3 "$SKILL_VALIDATOR" "$skill_dir" 2>&1)
+                validator_exit=$?
+                if [ $validator_exit -eq 0 ]; then
                     echo_success "Valid: $skill_md"
                 else
-                    echo_error "Validation failed: $skill_md"
+                    echo_error "Validation failed: $skill_md (exit code: $validator_exit)"
+                    echo "$validator_output"
                     VALIDATION_FAILED=1
                 fi
             done <<< "$STAGED_SKILL_FILES"

             if [ "$VALIDATION_FAILED" -eq 1 ]; then
                 echo_error "One or more skills failed validation."
                 echo_info "  Fix SKILL.md files and retry commit."
+                echo_info "  To skip validation (emergency only): SKIP_SKILL_VALIDATION=1 git commit ..."
                 EXIT_STATUS=1
             else
                 echo_success "All skill files validated successfully."
             fi
         else
             echo_error "Python 3 not available. Cannot validate skills."
             echo_info "  Install Python 3: https://www.python.org/downloads/"
+            echo_info "  To skip validation (emergency only): SKIP_SKILL_VALIDATION=1 git commit ..."
             EXIT_STATUS=1
         fi
-    else
-        echo_error "Skill validator not found: $SKILL_VALIDATOR"
-        EXIT_STATUS=1
     fi
+
+    fi  # End SKIP_SKILL_VALIDATION check
 else
     echo_info "No SKILL.md files staged. Skipping skill validation."
 fi
```

---

### Milestone 4: Documentation Alignment (IMPORTANT)

**Files**:
- `.agents/governance/skill-description-trigger-standard.md`

**Requirements**:
- Update Part 4: Validation to accurately describe what validator checks
- Clarify that Triggers section is RECOMMENDED not ERROR
- Note difference between full validation and minimal validation
- Remove any claims about features not actually implemented

**Acceptance Criteria**:
- Documentation matches actual validator behavior
- Triggers validation clearly marked as warning not error
- Difference between validate-skill.py and quick_validate.py explained

**Code Changes**:

Update Part 4 section to read:

```markdown
## Part 4: Validation

### Pre-Commit Validation (quick_validate.py)

The pre-commit hook uses `quick_validate.py` for minimal packaging validation:

1. SKILL.md exists
2. Valid YAML frontmatter
3. Only allowed properties in frontmatter: `name`, `description`, `license`, `allowed-tools`, `metadata`
4. Required fields present: `name` and `description`
5. Name format: hyphen-case, max 64 characters
6. Description format: max 1024 characters, no angle brackets

**Note**: This is minimal validation for packaging compatibility. It does NOT check body structure.

### Full Development Validation (validate-skill.py)

The full validator (`validate-skill.py`) provides development-time quality checks:

1. All quick_validate checks, plus:
2. Required frontmatter fields: `name`, `version`, `description`, `license`, `model`
3. Version format: semver (X.Y.Z)
4. Description word count: 10+ words (WARNING, not error)
5. **Triggers section**: RECOMMENDED (warning if missing, not blocking)
6. Process/Phases section: recommended
7. Verification/Success Criteria section: recommended
8. Anti-patterns section: recommended (warning)
9. Scripts documentation: if scripts/ exists, must have Scripts section

### Validation Levels

| Validator | Purpose | Checks | Exit Code |
|-----------|---------|--------|-----------|
| quick_validate.py | Pre-commit, packaging | Minimal (name, description, format) | 0=pass, 1=fail |
| validate-skill.py | Development quality | Full structural validation | 0=pass, 1=fail |

### Running Validation

```bash
# Quick validation (pre-commit uses this)
python .claude/skills/SkillForge/scripts/quick_validate.py path/to/skill/

# Full development validation
python .claude/skills/SkillForge/scripts/validate-skill.py path/to/skill/
```

### Skipping Pre-Commit Validation

In emergencies, skip skill validation:

```bash
SKIP_SKILL_VALIDATION=1 git commit -m "emergency fix"
```

**WARNING**: Only use in emergencies. Skipping validation may allow invalid skills.
```

---

## Milestone Dependencies

```
M1 (CodeQL) ---> M2 (Silent Failures)
                      |
                      +--> M3 (Pre-commit)
                      |
                      +--> M4 (Documentation)
```

M1 is blocking (security). M3 and M4 can run in parallel after M2.
