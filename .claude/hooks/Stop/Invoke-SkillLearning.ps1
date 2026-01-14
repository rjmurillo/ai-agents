<#
.SYNOPSIS
    Automatically extracts skill learnings from session conversation.

.DESCRIPTION
    Claude Code Stop hook that silently analyzes the conversation for
    skill-related learnings and updates skill memories automatically.

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

    Updates .serena/memories/skill-{name}.md files and outputs silent
    notifications like: "✔️learned from session ➡️github"

    This hook never blocks - session ends normally.

.NOTES
    Hook Type: Stop (non-blocking)
    Exit Codes:
        0 = Always (silent background learning)

    Related:
    - .claude/skills/reflect/SKILL.md
    - .serena/memories/skill-{name}.md
    - .claude-mem/memories/direct-backup-*.json (pattern source)

.LINK
    https://github.com/rjmurillo/ai-agents/pull/908
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'  # Silent operation

function Write-LearningNotification {
    param(
        [string]$SkillName,
        [int]$HighCount,
        [int]$MedCount,
        [int]$LowCount
    )

    $total = $HighCount + $MedCount + $LowCount
    if ($total -gt 0) {
        Write-Host "✔️ learned from session ➡️ $SkillName ($HighCount HIGH, $MedCount MED, $LowCount LOW)" -ForegroundColor Green
    }
}

function Get-ProjectDirectory {
    param($HookInput)

    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return $HookInput.cwd
}

function Get-ConversationMessages {
    param($HookInput)

    # Extract messages from hook input (conversation history)
    if ($HookInput.PSObject.Properties.Name -contains 'messages') {
        return $HookInput.messages
    }
    return @()
}

function Detect-SkillUsage {
    param([array]$Messages)

    # Detect skills mentioned or used in conversation
    $skillPatterns = @{
        'github' = @('gh pr', 'gh issue', '.claude/skills/github', 'github skill', '/pr-review')
        'memory' = @('search memory', 'forgetful', 'serena', 'memory-first', 'ADR-007')
        'session-init' = @('/session-init', 'session log', 'session protocol')
        'SkillForge' = @('SkillForge', 'create skill', 'synthesis panel')
        'adr-review' = @('adr-review', 'ADR files', 'architecture decision')
        'incoherence' = @('incoherence skill', 'detect incoherence', 'reconcile')
        'retrospective' = @('retrospective', 'session end', 'reflect')
        'reflect' = @('reflect', 'learn from this', 'what did we learn')
        'pr-comment-responder' = @('pr-comment-responder', 'review comments', 'feedback items')
        'code-review' = @('code review', 'style guide', 'security patterns')
        'api-design' = @('API design', 'REST', 'endpoint', 'versioning')
        'testing' = @('test', 'coverage', 'mocking', 'assertion')
        'documentation' = @('documentation', 'docs/', 'README', 'write doc')
    }

    $detectedSkills = @{}

    # Also detect skills from explicit references
    $conversationText = ($Messages | ForEach-Object { $_.content }) -join ' '

    # Detect skills referenced as .claude/skills/{skill-name}
    if ($conversationText -match '\.claude[/\\]skills[/\\]([a-z0-9-]+)') {
        $skillName = $Matches[1]
        if (-not $detectedSkills.ContainsKey($skillName)) {
            $detectedSkills[$skillName] = 1
        }
    }

    # Detect skills from slash commands
    if ($conversationText -match '/([a-z][a-z0-9-]+)') {
        $commandName = $Matches[1]
        # Map common commands to skills
        $commandToSkill = @{
            'pr-review' = 'github'
            'session-init' = 'session-init'
            'memory-search' = 'memory'
            'memory-list' = 'memory'
            'research' = 'research-and-incorporate'
        }
        if ($commandToSkill.ContainsKey($commandName)) {
            $skillName = $commandToSkill[$commandName]
            if (-not $detectedSkills.ContainsKey($skillName)) {
                $detectedSkills[$skillName] = 1
            }
        }
    }

    foreach ($skill in $skillPatterns.Keys) {
        $patterns = $skillPatterns[$skill]
        $matchCount = 0

        foreach ($msg in $Messages) {
            if ($msg.content) {
                foreach ($pattern in $patterns) {
                    if ($msg.content -match [regex]::Escape($pattern)) {
                        $matchCount++
                    }
                }
            }
        }

        if ($matchCount -ge 2) {  # Threshold: mentioned at least twice
            if ($detectedSkills.ContainsKey($skill)) {
                $detectedSkills[$skill] += $matchCount
            }
            else {
                $detectedSkills[$skill] = $matchCount
            }
        }
    }

    return $detectedSkills
}

function Extract-Learnings {
    param(
        [array]$Messages,
        [string]$SkillName
    )

    $learnings = @{
        High = @()
        Med = @()
        Low = @()
    }

    # Analyze messages for learning signals
    for ($i = 0; $i -lt $Messages.Count - 1; $i++) {
        $msg = $Messages[$i]
        $nextMsg = $Messages[$i + 1]

        if ($msg.role -eq 'assistant' -and $nextMsg.role -eq 'user') {
            $userResponse = $nextMsg.content

            # HIGH: Strong corrections and directives
            # Based on memory patterns: "no", "wrong", "incorrect", "fix", "never do", "always do", "must use"
            if ($userResponse -match '(?i)\b(no[,\s]|nope|not like that|that''s wrong|incorrect|never do|always do|don''t ever|must use|should not|avoid|stop)\b') {
                $learnings.High += @{
                    Type = 'correction'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # HIGH: Chesterton's Fence violations (removing things without understanding)
            if ($userResponse -match '(?i)(trashed without understanding|removed without knowing|deleted without checking|why was this here)') {
                $learnings.High += @{
                    Type = 'chestertons_fence'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # HIGH: Immediate corrections (commands right after output suggesting it was wrong)
            if ($userResponse -match '(?i)\b(debug|root cause|correct|fix all|address|broken|error|issue|problem)\b' -and $userResponse.Length -lt 200) {
                $learnings.High += @{
                    Type = 'immediate_correction'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # MED: Tool/approach preferences
            # Based on memory patterns: "instead", "rather than", "prefer", "should use"
            if ($userResponse -match '(?i)\b(instead of|rather than|prefer|should use|use .+ not|better to)\b') {
                $learnings.Med += @{
                    Type = 'preference'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # MED: Success patterns (expanded from memory analysis)
            if ($userResponse -match '(?i)\b(perfect|great|excellent|yes|exactly|that''s it|good job|well done|correct|right|works)\b') {
                $learnings.Med += @{
                    Type = 'success'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # MED: Edge cases and important questions
            # Based on memory patterns: "what if", "how does", "don't want to forget", "ensure", "make sure"
            if ($userResponse -match '(?i)(what if|how does|how will|what about|don''t want to forget|ensure|make sure|needs to)\?') {
                $learnings.Med += @{
                    Type = 'edge_case'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # MED: Simple questions after output (may indicate confusion or missing feature)
            if ($userResponse -match '\?' -and $userResponse.Length -lt 150) {
                $learnings.Med += @{
                    Type = 'question'
                    Source = $userResponse.Substring(0, [Math]::Min(150, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(150, $msg.content.Length))
                }
            }

            # LOW: Repeated commands or patterns (may become preferences)
            # Track for frequency analysis
            if ($userResponse -match '(?i)^(\.\/|pwsh |gh |git )') {
                $learnings.Low += @{
                    Type = 'command_pattern'
                    Source = $userResponse.Substring(0, [Math]::Min(100, $userResponse.Length))
                    Context = $msg.content.Substring(0, [Math]::Min(100, $msg.content.Length))
                }
            }
        }
    }

    return $learnings
}

function Update-SkillMemory {
    param(
        [string]$ProjectDir,
        [string]$SkillName,
        [hashtable]$Learnings,
        [string]$SessionId
    )

    $memoryPath = Join-Path $ProjectDir ".serena" "memories" "skill-$SkillName.md"
    $memoriesDir = Join-Path $ProjectDir ".serena" "memories"

    # Ensure directory exists
    if (-not (Test-Path $memoriesDir)) {
        New-Item -ItemType Directory -Path $memoriesDir -Force | Out-Null
    }

    # Read existing memory or create new
    $existingContent = ""
    if (Test-Path $memoryPath) {
        $existingContent = Get-Content $memoryPath -Raw
    }
    else {
        $existingContent = @"
# Skill Memory: $SkillName

**Last Updated**: $(Get-Date -Format "yyyy-MM-dd")
**Sessions Analyzed**: 0

## Constraints (HIGH confidence)

## Preferences (MED confidence)

## Edge Cases (MED confidence)

## Notes for Review (LOW confidence)

"@
    }

    # Append learnings
    $newContent = $existingContent

    if ($Learnings.High.Count -gt 0) {
        $constraintsSection = "## Constraints (HIGH confidence)`n"
        foreach ($learning in $Learnings.High) {
            $constraintsSection += "- $($learning.Source) (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        $newContent = $newContent -replace '(## Constraints \(HIGH confidence\))', "$constraintsSection`n"
    }

    if ($Learnings.Med.Count -gt 0) {
        foreach ($learning in $Learnings.Med) {
            if ($learning.Type -eq 'success') {
                $newContent += "`n- $($learning.Source) (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))"
            }
            elseif ($learning.Type -eq 'edge_case') {
                $newContent += "`n- Edge case: $($learning.Source) (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))"
            }
        }
    }

    # Update session count
    if ($newContent -match 'Sessions Analyzed: (\d+)') {
        $count = [int]$Matches[1] + 1
        $newContent = $newContent -replace 'Sessions Analyzed: \d+', "Sessions Analyzed: $count"
    }

    # Update last updated date
    $newContent = $newContent -replace '\*\*Last Updated\*\*: [\d-]+', "**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd')"

    # Write memory file
    Set-Content -Path $memoryPath -Value $newContent -Force

    return $true
}

try {
    # Check for piped input
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

    # Detect skills used in this session
    $detectedSkills = Detect-SkillUsage -Messages $messages

    if ($detectedSkills.Count -eq 0) {
        exit 0
    }

    # Get session ID from today's session log
    $sessionsDir = Join-Path $projectDir ".agents" "sessions"
    $today = Get-Date -Format "yyyy-MM-dd"
    $sessionLog = Get-ChildItem -Path $sessionsDir -Filter "$today-session-*.json" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    $sessionId = if ($sessionLog) {
        $sessionLog.BaseName
    }
    else {
        "$today-session-unknown"
    }

    # Process each detected skill
    foreach ($skillName in $detectedSkills.Keys) {
        $learnings = Extract-Learnings -Messages $messages -SkillName $skillName

        $highCount = $learnings.High.Count
        $medCount = $learnings.Med.Count
        $lowCount = $learnings.Low.Count

        # Only update if learnings meet threshold
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
    # Silent failure - don't block session end
    Write-Error "Skill learning hook error: $($_.Exception.Message)" -ErrorAction SilentlyContinue
    exit 0
}
