---
name: Feature Request - Claude Skill Installation Support
about: Add support for installing Claude skills in setup/installer scripts
title: "feat(install): Add Claude skill installation to installer scripts"
labels: enhancement, installer, claude-skills
assignees: ''
---

## Feature Request

### Summary

Add support for installing Claude skills from `.claude/skills/` directory to the installer scripts on supported platforms.

### Background

The ai-agents project now includes Claude skills (e.g., `.claude/skills/steering-matcher/`) that provide reusable PowerShell functions for agent workflows. These skills need to be properly installed and accessible on supported platforms.

### Platforms to Support

Research and implement Claude skill installation for:

1. **Claude Desktop** (if skills are supported)
2. **VS Code with Claude extension** (if applicable)
3. **GitHub Copilot CLI** (research if Claude skills are supported)

### Requirements

1. **Research Phase**
   - [ ] Investigate how Claude skills are installed/loaded on each platform
   - [ ] Document skill discovery mechanisms for each platform
   - [ ] Identify any platform-specific requirements or limitations

2. **Implementation Phase**
   - [ ] Update installer scripts to copy skills to appropriate locations
   - [ ] Add validation to ensure skills are accessible post-install
   - [ ] Document skill installation paths for each platform

3. **Documentation Phase**
   - [ ] Update installation instructions with skill setup
   - [ ] Add troubleshooting section for skill-related issues
   - [ ] Document how to create new skills

### Acceptance Criteria

- [ ] Installer scripts successfully install Claude skills on all supported platforms
- [ ] Skills are discoverable and usable by agents after installation
- [ ] Installation process is documented in README or installation guide
- [ ] Validation script confirms successful skill installation

### Related Files

- Claude skills: `.claude/skills/`
- Current installer scripts: `build/scripts/` or installation documentation
- Example skill: `.claude/skills/steering-matcher/`

### Additional Context

- Created as part of Phase 0 enhancement project (PR copilot/setup-foundational-structure)
- First skill: `steering-matcher` - matches files against steering glob patterns
- See `.agents/steering/README.md` for context on steering system

### Research Resources

- [Claude skill documentation](https://docs.anthropic.com/) (if available)
- GitHub Copilot custom instructions: https://docs.github.com/en/copilot/how-tos/configure-custom-instructions
- Platform-specific documentation for skill/extension loading

### Questions to Answer

1. Do all target platforms support Claude-style skills?
2. What is the skill discovery mechanism for each platform?
3. Are there naming or structure conventions we must follow?
4. Can skills be hot-reloaded or does the platform require restart?
