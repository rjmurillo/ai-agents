<#
.SYNOPSIS
    Pester tests for Verify-InstallOutput.ps1.

.DESCRIPTION
    Validates script structure, parameters, and expected module usage.
#>

BeforeAll {
    $Script:VerifyScript = Join-Path $PSScriptRoot "Verify-InstallOutput.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot "..\lib\Install-Common.psm1"
}

Describe "Verify-InstallOutput.ps1 Script Structure" {
    Context "File Existence" {
        It "Script file exists" {
            Test-Path $Script:VerifyScript | Should -Be $true
        }

        It "Module file exists" {
            Test-Path $Script:ModulePath | Should -Be $true
        }
    }

    Context "Help Documentation" {
        It "Has synopsis" {
            (Get-Content $Script:VerifyScript -Raw) | Should -Match "\.SYNOPSIS"
        }

        It "Has description" {
            (Get-Content $Script:VerifyScript -Raw) | Should -Match "\.DESCRIPTION"
        }

        It "Has examples" {
            (Get-Content $Script:VerifyScript -Raw) | Should -Match "\.EXAMPLE"
        }
    }
}

Describe "Verify-InstallOutput.ps1 Parameters" {
    BeforeAll {
        $Script:ScriptInfo = Get-Command $Script:VerifyScript
    }

    It "Defines Environment parameter with ValidateSet" {
        $Script:ScriptInfo.Parameters.ContainsKey("Environment") | Should -Be $true
        $validateSet = $Script:ScriptInfo.Parameters["Environment"].Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
        $validateSet.ValidValues | Should -Contain "Claude"
        $validateSet.ValidValues | Should -Contain "Copilot"
        $validateSet.ValidValues | Should -Contain "VSCode"
    }

    It "Defines Scope parameter with ValidateSet" {
        $Script:ScriptInfo.Parameters.ContainsKey("Scope") | Should -Be $true
        $validateSet = $Script:ScriptInfo.Parameters["Scope"].Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
        $validateSet.ValidValues | Should -Contain "Global"
        $validateSet.ValidValues | Should -Contain "Repo"
    }

    It "Defines RepoPath parameter as string" {
        $Script:ScriptInfo.Parameters.ContainsKey("RepoPath") | Should -Be $true
        $Script:ScriptInfo.Parameters["RepoPath"].ParameterType.Name | Should -Be "String"
    }

    It "Defines CI switch parameter" {
        $Script:ScriptInfo.Parameters.ContainsKey("CI") | Should -Be $true
        $Script:ScriptInfo.Parameters["CI"].SwitchParameter | Should -Be $true
    }
}

Describe "Verify-InstallOutput.ps1 Module Integration" {
    BeforeAll {
        $Script:Content = Get-Content $Script:VerifyScript -Raw
    }

    It "Imports Install-Common module" {
        $Script:Content | Should -Match "Install-Common\.psm1"
        $Script:Content | Should -Match "Import-Module"
    }

    It "Uses Get-InstallConfig and Resolve-DestinationPath" {
        $Script:Content | Should -Match "Get-InstallConfig"
        $Script:Content | Should -Match "Resolve-DestinationPath"
    }

    It "Uses Get-AgentFiles and Test-SourceDirectory" {
        $Script:Content | Should -Match "Get-AgentFiles"
        $Script:Content | Should -Match "Test-SourceDirectory"
    }
}
