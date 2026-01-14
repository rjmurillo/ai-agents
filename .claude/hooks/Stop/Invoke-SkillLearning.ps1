<#
.SYNOPSIS
    Automatically extracts skill learnings from session conversation.

.DESCRIPTION
    Claude Code Stop hook that silently analyzes the conversation for
    skill-related learnings and updates skill observation memories automatically.

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

    Updates .serena/memories/{skill-name}-observations.md files and outputs silent
    notifications like: "✔️learned from session ➡️github"

    This hook never blocks - session ends normally.

.NOTES
    Hook Type: Stop (non-blocking)
    Exit Codes:
        0 = Always (silent background learning)

    Related:
    - .claude/skills/reflect/SKILL.md
    - .serena/memories/{skill-name}-observations.md
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
    # Use Matches() to capture ALL skill references, not just the first
    $skillPathMatches = [regex]::Matches($conversationText, '\.claude[/\\]skills[/\\]([a-z0-9-]+)')
    foreach ($match in $skillPathMatches) {
        $skillName = $match.Groups[1].Value
        if (-not $detectedSkills.ContainsKey($skillName)) {
            $detectedSkills[$skillName] = 1
        }
        else {
            $detectedSkills[$skillName]++
        }
    }

    # Detect skills from slash commands
    # Use Matches() to capture ALL slash command references
    $slashCommandMatches = [regex]::Matches($conversationText, '/([a-z][a-z0-9-]+)')
    foreach ($match in $slashCommandMatches) {
        $commandName = $match.Groups[1].Value
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
            else {
                $detectedSkills[$skillName]++
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

    # Helper function to check if skill is mentioned in context
    function Test-SkillContext {
        param([string]$Text, [string]$Skill)
        # Check if the skill name or related patterns appear in the text
        # Use the same patterns from Detect-SkillUsage to ensure consistency
        $patterns = @{
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
            'documentation' = @('documentation', 'docs', 'readme', 'markdown')
        }

        if ($patterns.ContainsKey($Skill)) {
            foreach ($pattern in $patterns[$Skill]) {
                if ($Text -match [regex]::Escape($pattern)) {
                    return $true
                }
            }
        }
        return $false
    }

    # Analyze messages for learning signals
    for ($i = 0; $i -lt $Messages.Count - 1; $i++) {
        $msg = $Messages[$i]
        $nextMsg = $Messages[$i + 1]

        if ($msg.role -eq 'assistant' -and $nextMsg.role -eq 'user') {
            $userResponse = $nextMsg.content

            # Check if this learning is relevant to the current skill
            # by looking at the surrounding context (current and adjacent messages)
            $contextWindow = ""
            if ($i -gt 0) { $contextWindow += $Messages[$i - 1].content + " " }
            $contextWindow += $msg.content + " " + $userResponse
            if ($i + 2 -lt $Messages.Count) { $contextWindow += " " + $Messages[$i + 2].content }

            # Skip if skill is not mentioned in the context window
            if (-not (Test-SkillContext -Text $contextWindow -Skill $SkillName)) {
                continue
            }

            # HIGH: Strong corrections and directives
            # Based on memory patterns: "no", "wrong", "incorrect", "fix", "never do", "always do", "must use"
            # Pattern improved to match standalone "no" at word boundaries
            if ($userResponse -match '(?i)\b(no\b|nope|not like that|that''s wrong|incorrect|never do|always do|don''t ever|must use|should not|avoid|stop)\b') {
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

            # MED: Success patterns (approval at start of response)
            # Only match when approval words appear at the beginning to reduce false positives
            if ($userResponse -match '(?i)^(perfect|great|excellent|yes|exactly|that''s it|good job|well done|correct|right|works)\b') {
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

            # MED: Short clarifying questions after output (may indicate confusion)
            # Only capture very short questions to reduce noise
            if ($userResponse -match '\?' -and $userResponse.Length -lt 50 -and ($userResponse -match '(?i)^(why|how|what|when|where|can|does|is|are)\b')) {
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

    # Security: Path Traversal Prevention per CWE-22
    $allowedDir = [IO.Path]::GetFullPath($ProjectDir)
    $memoriesDir = Join-Path $allowedDir ".serena" "memories"
    $memoryPath = Join-Path $memoriesDir "$SkillName-observations.md"

    # Validate path is within project directory
    $resolvedPath = [IO.Path]::GetFullPath($memoryPath)
    if (-not $resolvedPath.StartsWith($allowedDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Warning "Path traversal attempt detected: '$resolvedPath' is outside the project directory."
        return $false
    }
    $memoryPath = $resolvedPath

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
# Skill Observations: $SkillName

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

    # Helper function to escape regex replacement strings
    function Escape-ReplacementString {
        param([string]$Text)
        # Escape $ characters to prevent regex backreference interpretation
        return $Text -replace '\$', '$$'
    }

    # HIGH: Append to Constraints section
    if ($Learnings.High.Count -gt 0) {
        $constraintItems = ""
        foreach ($learning in $Learnings.High) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $constraintItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        # Insert after header, preserving the header itself
        $newContent = $newContent -replace '(## Constraints \(HIGH confidence\)\r?\n)', "`$1$constraintItems"
    }

    # MED: Group by type and append to appropriate sections
    if ($Learnings.Med.Count -gt 0) {
        # Preferences: success patterns and tool preferences
        $preferenceItems = ""
        foreach ($learning in $Learnings.Med | Where-Object { $_.Type -in @('success', 'preference') }) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $preferenceItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        if ($preferenceItems) {
            $newContent = $newContent -replace '(## Preferences \(MED confidence\)\r?\n)', "`$1$preferenceItems"
        }

        # Edge Cases: edge case patterns and clarifying questions
        $edgeCaseItems = ""
        foreach ($learning in $Learnings.Med | Where-Object { $_.Type -in @('edge_case', 'question') }) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $edgeCaseItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        if ($edgeCaseItems) {
            $newContent = $newContent -replace '(## Edge Cases \(MED confidence\)\r?\n)', "`$1$edgeCaseItems"
        }
    }

    # LOW: Command patterns for frequency tracking
    if ($Learnings.Low.Count -gt 0) {
        $lowItems = ""
        foreach ($learning in $Learnings.Low) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $lowItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        if ($lowItems) {
            $newContent = $newContent -replace '(## Notes for Review \(LOW confidence\)\r?\n)', "`$1$lowItems"
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
