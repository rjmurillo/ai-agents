# Steering File Matcher Skill

## Purpose

PowerShell function to match file paths against steering file glob patterns and return applicable steering files sorted by priority.

## Usage

```powershell
# Load the skill
. .\.claude\skills\steering-matcher\Get-ApplicableSteering.ps1

# Get applicable steering for specific files
$files = @(
    "src/Auth/Controllers/TokenController.cs",
    "src/Auth/Services/TokenService.cs"
)
$steering = Get-ApplicableSteering -Files $files -SteeringPath ".agents/steering"

# Output: List of steering files sorted by priority
```

## Implementation

See `Get-ApplicableSteering.ps1` for the implementation.

## Integration

This skill is designed to be used by orchestrator agent in Phase 4 to determine which steering files to inject into agent context based on files affected by a task.

## Related

- [Steering System README](../../.agents/steering/README.md)
- [Enhancement Project Plan](../../.agents/planning/enhancement-PROJECT-PLAN.md)
