<#
.SYNOPSIS
    Shared types for session-init modules.

.DESCRIPTION
    Defines ApplicationFailedException used by GitHelpers and TemplateHelpers
    for wrapping unexpected errors with diagnostic context.

.NOTES
    Issue #840: Extracted from duplicate definitions in GitHelpers.psm1 and TemplateHelpers.psm1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ([System.Management.Automation.PSTypeName]'ApplicationFailedException').Type) {
    class ApplicationFailedException : System.ApplicationException {
        ApplicationFailedException([string]$Message, [Exception]$InnerException) : base($Message, $InnerException) {}
    }
}
