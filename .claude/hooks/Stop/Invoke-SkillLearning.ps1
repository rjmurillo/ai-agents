<#
.SYNOPSIS
    Automatically extracts skill learnings from session conversation.

.DESCRIPTION
    Claude Code Stop hook that silently analyzes the conversation for
    skill-related learnings and updates skill sidecar memories automatically.

    Detects all skills used in the session and extracts:

    HIGH CONFIDENCE (corrections - must fix):
    - Strong corrections: "no", "nope", "wrong", "incorrect", "never do", "must use"
    - Chesterton's Fence: "trashed without understanding", "removed without knowing"
    - Immediate fixes: "debug", "root cause", "fix all", "broken", "error"

    MEDIUM CONFIDENCE (patterns/preferences - should consider):
    - Tool preferences: "instead of", "rather than", "prefer", "should use"
    - Success patterns: "perfect", "great", "excellent", "yes", "exactly"
    - Edge cases: "what if", "how does", "don't want to forget", "ensure"
    - Questions: Any question after output (may indicate confusion)

    LOW CONFIDENCE (repeated patterns - track for frequency):
    - Command patterns: Repeated use of specific tools/commands

    Heuristics improved based on real memory patterns from .claude-mem backup analysis.

    Updates .serena/memories/{skill-name}-skill-sidecar-learnings.md files and outputs
    silent notifications like: "✔️ learned from session ➡️ github"

    This hook never blocks - session ends normally.

.NOTES
    Hook Type: Stop (non-blocking)
    Exit Codes:
        0 = Always (silent background learning)

    Related:
    - .claude/skills/reflect/SKILL.md
    - .serena/memories/{skill-name}-skill-sidecar-learnings.md
    - .claude-mem/memories/direct-backup-*.json (pattern source)

.LINK
    https://github.com/rjmurillo/ai-agents/pull/908
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'SkillLearning.Helpers.psm1') -Force

$SkillPatternMap = Get-DefaultSkillPatternMap
$SlashCommandSkillMap = Get-DefaultSlashCommandSkillMap

try {
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop
    $projectDir = Get-ProjectDirectory -HookInput $hookInput
    $messages = Get-ConversationMessages -HookInput $hookInput

    if ($messages.Count -eq 0) {
        exit 0
    }

    $detectedSkills = Detect-SkillUsage -Messages $messages -SkillPatternMap $SkillPatternMap -SlashCommandSkillMap $SlashCommandSkillMap

    if ($detectedSkills.Count -eq 0) {
        exit 0
    }

    $sessionsDir = Join-Path $projectDir '.agents' 'sessions'
    $today = Get-Date -Format 'yyyy-MM-dd'
    $sessionLog = Get-ChildItem -Path $sessionsDir -Filter "$today-session-*.json" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    $sessionId = if ($sessionLog) {
        $sessionLog.BaseName
    }
    else {
        "$today-session-unknown"
    }

    foreach ($skillName in $detectedSkills.Keys) {
        $learnings = Extract-Learnings -Messages $messages -SkillName $skillName -SkillPatternMap $SkillPatternMap

        $highCount = $learnings.High.Count
        $medCount = $learnings.Med.Count
        $lowCount = $learnings.Low.Count

        if ($highCount -ge 1 -or $medCount -ge 2 -or $lowCount -ge 3) {
            $updated = Update-SkillMemory -ProjectDir $projectDir -SkillName $skillName -Learnings $learnings -SessionId $sessionId

            if ($updated) {
                Write-LearningNotification -SkillName $skillName -HighCount $highCount -MedCount $medCount -LowCount $lowCount
            }
        }
    }

    exit 0
}
catch {
    Write-Error "Skill learning hook error: $($_.Exception.Message)" -ErrorAction SilentlyContinue
    exit 0
}
