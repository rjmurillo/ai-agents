Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:LearningPatterns = @{
    ExplicitCorrection = "(?i)\b(nope|not like that|that's wrong|this is wrong|wrong approach|incorrect|never do|always do|don't ever|do not|please don't|must use|should not|avoid (?:this|that|doing|using)|stop (?:this|that|doing|using))\b"
    ImmediateFix      = "(?i)\b(debug (?:this|that|it)|find the root cause|root cause (?:of|for)|fix (?:this|that|it|all of (?:this|it)|everything)|this is broken|that is broken|it's broken|please fix (?:this|that|it)|address (?:this|that|it) (?:bug|issue|error|problem)|resolve (?:this|that|it)|correct (?:this|that|it))\b"
    EdgeQuestion      = "(?i)(what if|how does|how will|what about).*\?"
    EdgeDirective     = "(?i)\b(don't want to forget|ensure|make sure|needs to)\b"
    Preference        = "(?i)\b(instead of|rather than|prefer|should use|use .+ not|better to)\b"
    Success           = "(?i)^(?:(?:ok|okay|yeah|yep|sure|alright)[,\s]+)?(perfect|great|excellent|exactly|that's it|good job|well done|works|yes(?!\s*,?\s*but)|correct(?!\s*,?\s*but)|right(?!\s*,?\s*about))\b"
    ShortQuestionLead = "(?i)^(why|how|what|when|where|can|does|is|are)\b"
    Chesterton        = "(?i)(trashed without understanding|removed without knowing|deleted without checking|why was this here)"
    CommandPattern    = "(?i)^(\.\/|pwsh |gh |git )"
}
$script:SoftNoIgnorePattern = "(?i)^\s*no\s+(problem|worries|issue|rush|need|idea|thanks|pressure|biggie)\b"

function Get-DefaultSkillPatternMap {
    [OutputType([hashtable])]
    param()

    return [ordered]@{
        'github'             = @('gh pr', 'gh issue', '.claude/skills/github', 'github skill', '/pr-review')
        'memory'             = @('search memory', 'forgetful', 'serena', 'memory-first', 'ADR-007')
        'session-init'       = @('/session-init', 'session log', 'session protocol')
        'SkillForge'         = @('SkillForge', 'create skill', 'synthesis panel')
        'adr-review'         = @('adr-review', 'ADR files', 'architecture decision')
        'incoherence'        = @('incoherence skill', 'detect incoherence', 'reconcile')
        'retrospective'      = @('retrospective', 'session end', 'reflect')
        'reflect'            = @('reflect', 'learn from this', 'what did we learn')
        'pr-comment-responder' = @('pr-comment-responder', 'review comments', 'feedback items')
        'code-review'        = @('code review', 'style guide', 'security patterns')
        'api-design'         = @('API design', 'REST', 'endpoint', 'versioning')
        'testing'            = @('test', 'coverage', 'mocking', 'assertion')
        'documentation'      = @('documentation', 'docs/', 'README', 'write doc')
    }
}

function Get-DefaultSlashCommandSkillMap {
    [OutputType([hashtable])]
    param()

    return @{
        'pr-review'    = 'github'
        'session-init' = 'session-init'
        'memory-search'= 'memory'
        'memory-list'  = 'memory'
        'research'     = 'research-and-incorporate'
    }
}

function Get-SkillSlug {
    [OutputType([string])]
    param([string]$SkillName)

    if ([string]::IsNullOrWhiteSpace($SkillName)) {
        return 'skill'
    }

    $slug = $SkillName.Trim().ToLowerInvariant()
    $slug = $slug -replace '[^a-z0-9]+', '-'
    $slug = $slug.Trim('-')

    if (-not $slug) {
        $slug = 'skill'
    }

    return $slug
}

function Get-SkillPatterns {
    [OutputType([string[]])]
    param(
        [string]$SkillName,
        [hashtable]$SkillPatternMap
    )

    $patterns = @()
    if ($SkillPatternMap.ContainsKey($SkillName)) {
        $patterns += $SkillPatternMap[$SkillName]
    }

    $slug = Get-SkillSlug -SkillName $SkillName
    $slugWithSpaces = $slug -replace '-', ' '

    $defaults = @(
        $SkillName,
        $slug,
        $slugWithSpaces,
        ".claude/skills/$slug",
        ".claude\skills\$slug"
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    $patterns += $defaults
    return $patterns | Select-Object -Unique
}

function Add-DetectedSkill {
    param(
        [hashtable]$DetectedSkills,
        [string]$SkillName,
        [int]$Increment = 1
    )

    if ([string]::IsNullOrWhiteSpace($SkillName)) {
        return
    }

    $valueToAdd = [Math]::Max(1, [Math]::Abs($Increment))
    if ($DetectedSkills.ContainsKey($SkillName)) {
        $DetectedSkills[$SkillName] += $valueToAdd
    }
    else {
        $DetectedSkills[$SkillName] = $valueToAdd
    }
}

function Test-SkillContext {
    [OutputType([bool])]
    param(
        [string]$Text,
        [string]$Skill,
        [hashtable]$SkillPatternMap
    )

    $patterns = Get-SkillPatterns -SkillName $Skill -SkillPatternMap $SkillPatternMap
    if ($patterns.Count -eq 0) {
        return $true
    }

    foreach ($pattern in $patterns) {
        if ([string]::IsNullOrWhiteSpace($pattern)) {
            continue
        }

        if ($Text -match [regex]::Escape($pattern)) {
            return $true
        }
    }

    return $false
}

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

    if ($HookInput.PSObject.Properties.Name -contains 'messages') {
        return $HookInput.messages
    }
    return @()
}

function Detect-SkillUsage {
    [OutputType([hashtable])]
    param(
        [array]$Messages,
        [hashtable]$SkillPatternMap,
        [hashtable]$SlashCommandSkillMap
    )

    $detectedSkills = @{}
    $conversationText = ($Messages | ForEach-Object { $_.content }) -join ' '

    $skillPathMatches = [regex]::Matches($conversationText, '\.claude[/\\]skills[/\\]([a-z0-9-]+)')
    foreach ($match in $skillPathMatches) {
        $skillName = $match.Groups[1].Value
        Add-DetectedSkill -DetectedSkills $detectedSkills -SkillName $skillName
    }

    $slashCommandMatches = [regex]::Matches($conversationText, '/([a-z][a-z0-9-]+)')
    foreach ($match in $slashCommandMatches) {
        $commandName = $match.Groups[1].Value
        if ($SlashCommandSkillMap.ContainsKey($commandName)) {
            $skillName = $SlashCommandSkillMap[$commandName]
            Add-DetectedSkill -DetectedSkills $detectedSkills -SkillName $skillName
        }
    }

    foreach ($skill in $SkillPatternMap.Keys) {
        $patterns = Get-SkillPatterns -SkillName $skill -SkillPatternMap $SkillPatternMap
        $matchCount = 0

        foreach ($msg in $Messages) {
            if (-not $msg.content) { continue }

            foreach ($pattern in $patterns) {
                if ($msg.content -match [regex]::Escape($pattern)) {
                    $matchCount++
                }
            }
        }

        if ($matchCount -ge 2) {
            Add-DetectedSkill -DetectedSkills $detectedSkills -SkillName $skill -Increment $matchCount
        }
    }

    return $detectedSkills
}

function Get-LearningContextWindow {
    [OutputType([string])]
    param(
        [array]$Messages,
        [int]$Index
    )

    $builder = [System.Text.StringBuilder]::new()
    if ($Index -gt 0) {
        [void]$builder.Append($Messages[$Index - 1].content + ' ')
    }

    [void]$builder.Append($Messages[$Index].content + ' ')

    $userIndex = $Index + 1
    if ($userIndex -lt $Messages.Count) {
        [void]$builder.Append($Messages[$userIndex].content)
    }

    if ($userIndex + 1 -lt $Messages.Count) {
        [void]$builder.Append(' ' + $Messages[$userIndex + 1].content)
    }

    return $builder.ToString()
}

function Test-StartsWithStrongNo {
    [OutputType([bool])]
    param([string]$UserResponse)

    return ($UserResponse -match '(?i)^\s*no\b') -and -not ($UserResponse -match $script:SoftNoIgnorePattern)
}

function New-LearningEntry {
    [OutputType([hashtable])]
    param(
        [string]$Type,
        [string]$UserResponse,
        [string]$AssistantContent,
        [int]$SourceLimit = 150,
        [int]$ContextLimit = 150
    )

    return @{
        Type    = $Type
        Source  = $UserResponse.Substring(0, [Math]::Min($SourceLimit, $UserResponse.Length))
        Context = $AssistantContent.Substring(0, [Math]::Min($ContextLimit, $AssistantContent.Length))
    }
}

function Add-HighConfidenceLearnings {
    param(
        [string]$UserResponse,
        [string]$AssistantContent,
        [hashtable]$Learnings
    )

    if (Test-StartsWithStrongNo -UserResponse $UserResponse -and -not ($UserResponse -match $script:LearningPatterns.ExplicitCorrection)) {
        $Learnings.High += (New-LearningEntry -Type 'correction' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }
    elseif ($UserResponse -match $script:LearningPatterns.ExplicitCorrection) {
        $Learnings.High += (New-LearningEntry -Type 'correction' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }

    if ($UserResponse -match $script:LearningPatterns.Chesterton) {
        $Learnings.High += (New-LearningEntry -Type 'chestertons_fence' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }

    if ($UserResponse -match $script:LearningPatterns.ImmediateFix) {
        $Learnings.High += (New-LearningEntry -Type 'immediate_correction' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }
}

function Add-MediumConfidenceLearnings {
    param(
        [string]$UserResponse,
        [string]$AssistantContent,
        [hashtable]$Learnings
    )

    if ($UserResponse -match $script:LearningPatterns.Preference) {
        $Learnings.Med += (New-LearningEntry -Type 'preference' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }

    if ($UserResponse -match $script:LearningPatterns.Success) {
        $Learnings.Med += (New-LearningEntry -Type 'success' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }

    $edgeQuestion = $UserResponse -match $script:LearningPatterns.EdgeQuestion
    $edgeDirective = $UserResponse -match $script:LearningPatterns.EdgeDirective
    if ($edgeQuestion -or $edgeDirective) {
        $Learnings.Med += (New-LearningEntry -Type 'edge_case' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }

    if ($UserResponse -match '\?' -and $UserResponse.Length -lt 50 -and ($UserResponse -match $script:LearningPatterns.ShortQuestionLead)) {
        $Learnings.Med += (New-LearningEntry -Type 'question' -UserResponse $UserResponse -AssistantContent $AssistantContent)
    }
}

function Add-LowConfidenceLearnings {
    param(
        [string]$UserResponse,
        [string]$AssistantContent,
        [hashtable]$Learnings
    )

    if ($UserResponse -match $script:LearningPatterns.CommandPattern) {
        $Learnings.Low += (New-LearningEntry -Type 'command_pattern' -UserResponse $UserResponse -AssistantContent $AssistantContent -SourceLimit 100 -ContextLimit 100)
    }
}

function Extract-Learnings {
    [OutputType([hashtable])]
    param(
        [array]$Messages,
        [string]$SkillName,
        [hashtable]$SkillPatternMap
    )

    $learnings = @{
        High = @()
        Med  = @()
        Low  = @()
    }

    for ($i = 0; $i -lt $Messages.Count - 1; $i++) {
        $assistantMessage = $Messages[$i]
        $userMessage = $Messages[$i + 1]

        if ($assistantMessage.role -ne 'assistant' -or $userMessage.role -ne 'user') {
            continue
        }

        $contextWindow = Get-LearningContextWindow -Messages $Messages -Index $i
        if (-not (Test-SkillContext -Text $contextWindow -Skill $SkillName -SkillPatternMap $SkillPatternMap)) {
            continue
        }

        Add-HighConfidenceLearnings -UserResponse $userMessage.content -AssistantContent $assistantMessage.content -Learnings $learnings
        Add-MediumConfidenceLearnings -UserResponse $userMessage.content -AssistantContent $assistantMessage.content -Learnings $learnings
        Add-LowConfidenceLearnings -UserResponse $userMessage.content -AssistantContent $assistantMessage.content -Learnings $learnings
    }

    return $learnings
}

function Escape-ReplacementString {
    [OutputType([string])]
    param([string]$Text)

    return $Text -replace '\$', '$$'
}

function Update-SkillMemory {
    [OutputType([bool])]
    param(
        [string]$ProjectDir,
        [string]$SkillName,
        [hashtable]$Learnings,
        [string]$SessionId
    )

    $allowedDir = [IO.Path]::GetFullPath($ProjectDir)
    $memoriesDir = Join-Path $allowedDir ".serena" "memories"
    $memoryFileName = "{0}-skill-sidecar-learnings.md" -f (Get-SkillSlug -SkillName $SkillName)
    $memoryPath = Join-Path $memoriesDir $memoryFileName

    $resolvedPath = [IO.Path]::GetFullPath($memoryPath)
    if (-not $resolvedPath.StartsWith($allowedDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Warning "Path traversal attempt detected: '$resolvedPath' is outside the project directory."
        return $false
    }
    $memoryPath = $resolvedPath

    if (-not (Test-Path $memoriesDir)) {
        New-Item -ItemType Directory -Path $memoriesDir -Force | Out-Null
    }

    if (-not (Test-Path $memoryPath)) {
        $template = @"
# Skill Sidecar Learnings: $SkillName

**Last Updated**: $(Get-Date -Format "yyyy-MM-dd")
**Sessions Analyzed**: 0

## Constraints (HIGH confidence)

## Preferences (MED confidence)

## Edge Cases (MED confidence)

## Notes for Review (LOW confidence)

"@
        Set-Content -Path $memoryPath -Value $template -Force
    }

    $newContent = Get-Content $memoryPath -Raw

    if ($Learnings.High.Count -gt 0) {
        $constraintItems = ''
        foreach ($learning in $Learnings.High) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $constraintItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        $newContent = $newContent -replace '(## Constraints \(HIGH confidence\)\r?\n)', "`$1$constraintItems"
    }

    if ($Learnings.Med.Count -gt 0) {
        $preferenceItems = ''
        foreach ($learning in $Learnings.Med | Where-Object { $_.Type -in @('success', 'preference') }) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $preferenceItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        if ($preferenceItems) {
            $newContent = $newContent -replace '(## Preferences \(MED confidence\)\r?\n)', "`$1$preferenceItems"
        }

        $edgeCaseItems = ''
        foreach ($learning in $Learnings.Med | Where-Object { $_.Type -in @('edge_case', 'question') }) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $edgeCaseItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        if ($edgeCaseItems) {
            $newContent = $newContent -replace '(## Edge Cases \(MED confidence\)\r?\n)', "`$1$edgeCaseItems"
        }
    }

    if ($Learnings.Low.Count -gt 0) {
        $lowItems = ''
        foreach ($learning in $Learnings.Low) {
            $escapedSource = Escape-ReplacementString $learning.Source
            $lowItems += "- $escapedSource (Session $SessionId, $(Get-Date -Format 'yyyy-MM-dd'))`n"
        }
        if ($lowItems) {
            $newContent = $newContent -replace '(## Notes for Review \(LOW confidence\)\r?\n)', "`$1$lowItems"
        }
    }

    if ($newContent -match '\*\*Sessions Analyzed\*\*: (\d+)') {
        $count = [int]$Matches[1] + 1
        $newContent = $newContent -replace '\*\*Sessions Analyzed\*\*: \d+', "**Sessions Analyzed**: $count"
    }
    elseif ($newContent -match 'Sessions Analyzed: (\d+)') {
        $count = [int]$Matches[1] + 1
        $newContent = $newContent -replace 'Sessions Analyzed: \d+', "Sessions Analyzed: $count"
    }

    $newContent = $newContent -replace '\*\*Last Updated\*\*: [\d-]+', "**Last Updated**: $(Get-Date -Format 'yyyy-MM-dd')"

    Set-Content -Path $memoryPath -Value $newContent -Force
    return $true
}

Export-ModuleMember -Function @(
        'Get-DefaultSkillPatternMap'
        'Get-DefaultSlashCommandSkillMap'
        'Get-SkillSlug'
        'Get-SkillPatterns'
        'Test-SkillContext'
        'Write-LearningNotification'
        'Get-ProjectDirectory'
        'Get-ConversationMessages'
        'Detect-SkillUsage'
        'Extract-Learnings'
        'Update-SkillMemory'
    )
