#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Post-PRCommentReply.ps1

.DESCRIPTION
    Validates parameter handling, error conditions, and repo inference.
    Note: Actual API calls are not tested to avoid side effects.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "Post-PRCommentReply.ps1"
}

Describe "Post-PRCommentReply.ps1 Parameter Validation" {

    Context "Required Parameters" {
        It "Requires PullRequest parameter" {
            { & $ScriptPath -Body "test" } | Should -Throw "*PullRequest*"
        }

        It "Requires Body or BodyFile parameter" {
            { & $ScriptPath -PullRequest 50 } | Should -Throw
        }
    }

    Context "Mutually Exclusive Parameters" {
        It "Accepts Body parameter in BodyText parameter set" {
            # This will fail at runtime due to gh, but parameter binding should succeed
            $cmd = Get-Command $ScriptPath
            $cmd.Parameters['Body'].ParameterSets.Keys | Should -Contain "BodyText"
        }

        It "Accepts BodyFile parameter in BodyFile parameter set" {
            $cmd = Get-Command $ScriptPath
            $cmd.Parameters['BodyFile'].ParameterSets.Keys | Should -Contain "BodyFile"
        }
    }

    Context "CommentType Validation" {
        It "Validates CommentType accepts 'review'" {
            $cmd = Get-Command $ScriptPath
            $validateSet = $cmd.Parameters['CommentType'].Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet.ValidValues | Should -Contain "review"
        }

        It "Validates CommentType accepts 'issue'" {
            $cmd = Get-Command $ScriptPath
            $validateSet = $cmd.Parameters['CommentType'].Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet.ValidValues | Should -Contain "issue"
        }
    }
}

Describe "Post-PRCommentReply.ps1 Error Handling" {

    Context "BodyFile Validation" {
        It "Exits with code 2 when body file does not exist" {
            $result = pwsh -Command "& '$ScriptPath' -PullRequest 50 -CommentId 12345 -BodyFile 'nonexistent-file-12345.md'; exit `$LASTEXITCODE" 2>&1
            $LASTEXITCODE | Should -Be 2
        }
    }

    Context "CommentId Validation" {
        It "Exits with code 1 when CommentId missing for review type" {
            $result = pwsh -Command "& '$ScriptPath' -PullRequest 50 -CommentType 'review' -Body 'test'; exit `$LASTEXITCODE" 2>&1
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "Empty Body Validation" {
        BeforeAll {
            $emptyFile = Join-Path $TestDrive "empty.md"
            "" | Set-Content $emptyFile
        }

        It "Exits with code 1 when body file contains only whitespace" {
            $whitespaceFile = Join-Path $TestDrive "whitespace.md"
            "   " | Set-Content $whitespaceFile
            $result = pwsh -Command "& '$ScriptPath' -PullRequest 50 -BodyFile '$whitespaceFile'; exit `$LASTEXITCODE" 2>&1
            $LASTEXITCODE | Should -Be 1
        }
    }
}

Describe "Post-PRCommentReply.ps1 Repo Inference" {

    Context "Git Remote Parsing" {
        It "Has Get-RepoInfo helper function defined" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Get-RepoInfo"
        }

        It "Handles HTTPS GitHub URLs" {
            $content = Get-Content $ScriptPath -Raw
            # Regex should match github.com[:/] - escaping the brackets for PowerShell regex
            $content | Should -Match 'github\\\.com\[:/\]'
        }

        It "Handles SSH GitHub URLs" {
            $content = Get-Content $ScriptPath -Raw
            # Same regex handles both via [:/]
            $content | Should -Match "\[:/\]"
        }
    }
}

Describe "Post-PRCommentReply.ps1 Comment Type Detection" {

    Context "Auto-detection Logic" {
        It "Defaults to review type when CommentId is provided" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'if \(\$CommentId\) \{ "review" \}'
        }

        It "Defaults to issue type when CommentId is not provided" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'else \{ "issue" \}'
        }
    }
}

Describe "Post-PRCommentReply.ps1 API Endpoints" {

    Context "Review Comment Reply" {
        It "Uses correct API endpoint for review replies" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'repos/\$Owner/\$Repo/pulls/\$PullRequest/comments'
        }

        It "Uses in_reply_to parameter for review replies" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'in_reply_to=\$CommentId'
        }
    }

    Context "Issue Comment (Top-level)" {
        It "Uses correct API endpoint for issue comments" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'repos/\$Owner/\$Repo/issues/\$PullRequest/comments'
        }
    }
}

Describe "Post-PRCommentReply.ps1 Help Documentation" {

    Context "Help Content" {
        BeforeAll {
            $help = Get-Help $ScriptPath -Full
        }

        It "Has synopsis" {
            $help.Synopsis | Should -Not -BeNullOrEmpty
        }

        It "Has description" {
            $help.Description | Should -Not -BeNullOrEmpty
        }

        It "Has examples" {
            $help.Examples.Example.Count | Should -BeGreaterThan 0
        }

        It "Documents all parameters" {
            $help.Parameters.Parameter | Where-Object { $_.Name -eq 'PullRequest' } | Should -Not -BeNullOrEmpty
            $help.Parameters.Parameter | Where-Object { $_.Name -eq 'CommentId' } | Should -Not -BeNullOrEmpty
            $help.Parameters.Parameter | Where-Object { $_.Name -eq 'Body' } | Should -Not -BeNullOrEmpty
            $help.Parameters.Parameter | Where-Object { $_.Name -eq 'BodyFile' } | Should -Not -BeNullOrEmpty
        }

        It "Documents exit codes in notes" {
            $help.alertSet.alert.Text | Should -Match "Exit Codes"
        }

        It "Has related links" {
            $help.relatedLinks | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "Post-PRCommentReply.ps1 Output Format" {

    Context "Success Output Structure" {
        It "Returns PSCustomObject with expected properties" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\[PSCustomObject\]@\{'
            $content | Should -Match 'Success\s*='
            $content | Should -Match 'CommentId\s*='
            $content | Should -Match 'HtmlUrl\s*='
            $content | Should -Match 'CreatedAt\s*='
            $content | Should -Match 'CommentType\s*='
        }
    }
}
