<#
.SYNOPSIS
    Registers Windows Scheduled Tasks for the Darwin Trader local CLI pipeline.

.DESCRIPTION
    Registers four autonomous nodes under Windows Task Scheduler:
      1. DT-BacklogTriage:       Runs run-backlog-triage.ps1 every 6 hours
      2. DT-PRReview:            Runs run-pr-review.ps1 every 5 minutes
      3. DT-Architect:           Runs run-architect.ps1 every 5 minutes
      4. DT-ThreeAmigosDevTest:  Runs run-three-amigos-and-dev-test.ps1 every 15 minutes

    All tasks are configured with:
      - MultipleInstances: IgnoreNew (single-flight)
      - StartWhenAvailable: $true (catch up if machine was asleep)
      - Logged-on user session execution

.EXAMPLE
    .\scripts\local-pipeline\register-local-tasks.ps1
#>
param(
    [switch]$Unregister
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LocalPipelineDir = Join-Path $RepoRoot "scripts\local-pipeline"

$Tasks = @(
    @{
        Name     = "DT-BacklogTriage"
        Script   = (Join-Path $LocalPipelineDir "run-backlog-triage.ps1")
        Interval = (New-TimeSpan -Hours 6)
        Duration = (New-TimeSpan -Days 3650)
    },
    @{
        Name     = "DT-PRReview"
        Script   = (Join-Path $LocalPipelineDir "run-pr-review.ps1")
        Interval = (New-TimeSpan -Minutes 5)
        Duration = (New-TimeSpan -Days 3650)
    },
    @{
        Name     = "DT-Architect"
        Script   = (Join-Path $LocalPipelineDir "run-architect.ps1")
        Interval = (New-TimeSpan -Minutes 5)
        Duration = (New-TimeSpan -Days 3650)
    },
    @{
        Name     = "DT-ThreeAmigosDevTest"
        Script   = (Join-Path $LocalPipelineDir "run-three-amigos-and-dev-test.ps1")
        Interval = (New-TimeSpan -Minutes 15)
        Duration = (New-TimeSpan -Days 3650)
    }
)

if ($Unregister) {
    foreach ($task in $Tasks) {
        $name = $task.Name
        Write-Host "Unregistering scheduled task '$name'..."
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    }
    Write-Host "All Darwin Trader tasks unregistered."
    return
}

foreach ($task in $Tasks) {
    $name = $task.Name
    $script = $task.Script
    $interval = $task.Interval
    $duration = $task.Duration

    Write-Host "Registering scheduled task '$name' ($($interval.TotalMinutes) min interval)..."

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
        -WorkingDirectory $RepoRoot

    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval $interval `
        -RepetitionDuration $duration

    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries

    Register-ScheduledTask `
        -TaskName $name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Force | Out-Null

    Write-Host "  -> Registered '$name' successfully."
}

Write-Host "`nAll Darwin Trader local pipeline tasks registered successfully."
