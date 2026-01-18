@{
    # Use default rules plus custom rules specified
    # Note: Not using IncludeRules as it restricts to only those rules
    # Instead, we enable all default rules and configure specific ones in the Rules section
    
    # Consistent indentation settings
    Rules = @{
        PSUseConsistentIndentation = @{
            Enable = $true
            IndentationSize = 4
            PipelineIndentation = 'IncreaseIndentationForFirstPipeline'
            Kind = 'space'
        }
        
        PSUseConsistentWhitespace = @{
            Enable = $true
            CheckInnerBrace = $true
            CheckOpenBrace = $true
            CheckOpenParen = $true
            CheckOperator = $true
            CheckPipe = $true
            CheckPipeForRedundantWhitespace = $false
            CheckSeparator = $true
            CheckParameter = $false
        }
        
        PSAvoidUsingCmdletAliases = @{
            Enable = $true
        }
        
        PSAvoidUsingPositionalParameters = @{
            Enable = $true
            CommandAllowList = @()
        }
        
        PSAvoidUsingInvokeExpression = @{
            Enable = $true
        }
    }

    # Exclude specific rules for user-facing scripts where Write-Host is appropriate
    ExcludeRules = @(
        # Write-Host is acceptable in installation/scan scripts for colored console output
        # These scripts are meant for direct user interaction, not pipeline use
        'PSAvoidUsingWriteHost'
    )
}
