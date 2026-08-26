<#
.SYNOPSIS
    Local Windows Task Scheduler replacement for the Antigravity "Backlog
    Triage" scheduled task -- Fetch -> Gate -> Judge -> Act, judgment-only LLM call.

.DESCRIPTION
    Design: ws-setups/graph-engineering/docs/backlog-triage-node.md

    Runs the same per-label procedure as the old fully-agentic
    `.antigravity/tasks/backlog-triage.md`, but splits it so the LLM is
    only ever asked to do the one thing that genuinely needs judgment
    (clustering + story synthesis), while every deterministic step
    (listing issues, creating/commenting/closing them, syncing the
    checkout) runs as plain PowerShell/gh:

      1. Fetch  - `gh issue list` per label (never mixed).
      2. Gate   - if every label came back empty, exit 0 without ever
                  invoking agy.exe. A poll with nothing to do must cost
                  zero LLM tokens.
      3. Judge  - one short `agy.exe --print` call per non-empty label,
                  using the judgment-only prompt template at
                  `.antigravity/tasks/backlog-triage.md`.
      4. Act    - create one `type:user-story` issue per returned
                  cluster, then comment+close every absorbed source issue.

    Labels are always processed independently, one at a time, so a
    cluster/story never absorbs issues from more than one label.

.EXAMPLE
    .\scripts\local-pipeline\run-backlog-triage.ps1
#>
param(
    [string]$Repo = "AntaresAndBharani/darwin-trader",
    [string]$AgyPath = "C:\Users\rogal\AppData\Local\agy\bin\agy.exe",
    [string]$Model = "gemini-3.7-flash-medium",
    [string[]]$Labels = @("tech-debt", "enhancement"),
    [string]$PromptTemplatePath = (Join-Path $PSScriptRoot "..\..\.antigravity\tasks\backlog-triage.md")
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs\local-pipeline"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir ("backlog-triage-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding utf8
}

function Get-OpenIssuesForLabel {
    param([string]$Label)

    Write-Log "Fetching open issues for label '$Label'..."
    $raw = $null
    try {
        $raw = gh issue list --repo $Repo --label $Label --state open --json number,title,body 2>&1
    } catch {
        Write-Log "gh issue list threw for label '${Label}': $_" "ERROR"
        throw
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh issue list exited $LASTEXITCODE for label '${Label}': $raw" "ERROR"
        throw "gh issue list failed for label '$Label'"
    }

    $issues = @()
    $rawText = ConvertTo-SafeString $raw
    if (-not [string]::IsNullOrWhiteSpace($rawText)) {
        try {
            $parsed = $rawText | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Log "Failed to parse gh issue list JSON for label '${Label}': $_. Raw: $rawText" "ERROR"
            throw
        }
        if ($null -ne $parsed) {
            foreach ($item in @($parsed)) {
                if ($null -ne $item) { $issues += $item }
            }
        }
    }

    Write-Log "Fetched $($issues.Count) open issue(s) for label '$Label'."
    return , $issues
}

function ConvertTo-SafeString {
    param($InputObject)
    if ($null -eq $InputObject) { return "" }
    if ($InputObject -is [string]) { return $InputObject }
    if ($InputObject -is [System.Collections.IEnumerable]) {
        $parts = @()
        foreach ($item in $InputObject) {
            if ($null -ne $item) { $parts += $item.ToString() }
        }
        return ($parts -join "`n")
    }
    return $InputObject.ToString()
}

function ConvertTo-EscapedArgument {
    param([string]$Arg)
    if ($Arg -eq "") { return '""' }
    if ($Arg -notmatch '[\s"]') { return $Arg }
    $result = '"'
    $backslashes = 0
    foreach ($ch in $Arg.ToCharArray()) {
        if ($ch -eq '\') {
            $backslashes++
        } elseif ($ch -eq '"') {
            $result += ('\' * ($backslashes * 2 + 1))
            $result += '"'
            $backslashes = 0
        } else {
            if ($backslashes -gt 0) {
                $result += ('\' * $backslashes)
                $backslashes = 0
            }
            $result += $ch
        }
    }
    if ($backslashes -gt 0) {
        $result += ('\' * ($backslashes * 2))
    }
    $result += '"'
    return $result
}

function Invoke-NativeProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $escapedArgs = @()
    foreach ($arg in $ArgumentList) {
        $escapedArgs += (ConvertTo-EscapedArgument $arg)
    }
    $cmdLine = ($escapedArgs -join " ")

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $cmdLine
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi

    $stdoutBuilder = New-Object System.Text.StringBuilder
    $stderrBuilder = New-Object System.Text.StringBuilder

    $outHandler = {
        if ($EventArgs.Data) {
            [void]$Event.MessageData.AppendLine($EventArgs.Data)
        }
    }
    $errHandler = {
        if ($EventArgs.Data) {
            [void]$Event.MessageData.AppendLine($EventArgs.Data)
        }
    }

    $outEvent = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action $outHandler -MessageData $stdoutBuilder
    $errEvent = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -Action $errHandler -MessageData $stderrBuilder

    try {
        [void]$proc.Start()
        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()
        $proc.WaitForExit()
    } finally {
        Unregister-Event -SourceIdentifier $outEvent.Name -ErrorAction SilentlyContinue
        Unregister-Event -SourceIdentifier $errEvent.Name -ErrorAction SilentlyContinue
    }

    $exitCode = $proc.ExitCode
    $stdout = $stdoutBuilder.ToString()
    $stderr = $stderrBuilder.ToString()

    return [PSCustomObject]@{
        ExitCode = $exitCode
        StdOut   = $stdout
        StdErr   = $stderr
    }
}

function Sync-Checkout {
    Write-Log "Syncing local git checkout with origin/main..."
    Push-Location $RepoRoot
    try {
        $prevEA = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $null = git checkout main 2>&1
            $null = git fetch origin 2>&1
            $null = git reset --hard origin/main 2>&1
        } finally {
            $ErrorActionPreference = $prevEA
        }
    } finally {
        Pop-Location
    }
    Write-Log "Checkout synced."
}

function Run-TriageForLabel {
    param(
        [string]$Label,
        [array]$Issues
    )

    Write-Log "--- Triaging label '$Label' ($($Issues.Count) issue(s)) ---"

    if (-not (Test-Path -LiteralPath $PromptTemplatePath)) {
        throw "Prompt template not found at '$PromptTemplatePath'"
    }
    $template = Get-Content -LiteralPath $PromptTemplatePath -Raw -Encoding utf8

    $issuesJson = $Issues | ConvertTo-Json -Depth 5
    $prompt = $template.Replace("{{LABEL}}", $Label).Replace("{{ISSUES_JSON}}", $issuesJson)

    Write-Log "Invoking agy.exe (model: $Model, prompt chars: $($prompt.Length))..."

    $args = @(
        "--model", $Model,
        "--output-format", "json",
        "--print", $prompt
    )

    $result = Invoke-NativeProcess -FilePath $AgyPath -ArgumentList $args

    if ($result.ExitCode -ne 0) {
        Write-Log "agy.exe exited with code $($result.ExitCode). Stderr: $($result.StdErr)" "ERROR"
        throw "agy.exe failed (exit code $($result.ExitCode))"
    }

    $stdout = $result.StdOut
    if ([string]::IsNullOrWhiteSpace($stdout)) {
        throw "agy.exe returned empty stdout."
    }

    $envelope = $null
    try {
        $envelope = $stdout | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed to parse agy.exe JSON envelope: $_. Stdout: $stdout" "ERROR"
        throw
    }

    $rawText = $envelope.response
    if ([string]::IsNullOrWhiteSpace($rawText)) {
        throw "agy.exe envelope contained no 'response' field."
    }

    $jsonText = $rawText.Trim()
    if ($jsonText -match '(?s)```(?:json)?\s*(.*?)\s*```') {
        $jsonText = $Matches[1].Trim()
    }

    $clusters = $null
    try {
        $clusters = $jsonText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed to parse clusters JSON: $_. Cleaned text: $jsonText" "ERROR"
        throw
    }

    if ($null -eq $clusters) {
        Write-Log "Clusters array parsed as null." "WARN"
        return
    }

    $clusterList = @()
    foreach ($c in @($clusters)) {
        if ($null -ne $c) { $clusterList += $c }
    }

    Write-Log "Judge synthesized $($clusterList.Count) cluster(s)."

    # 4. Act step
    foreach ($cluster in $clusterList) {
        $title = $cluster.story_title
        $body = $cluster.story_body
        $absorbed = @($cluster.absorbed_issue_numbers)

        if ([string]::IsNullOrWhiteSpace($title) -or [string]::IsNullOrWhiteSpace($body)) {
            Write-Log "Skipping cluster with empty title or body." "WARN"
            continue
        }

        Write-Log "Creating story: '$title' (absorbing: $($absorbed -join ', '))..."

        $tempFile = [System.IO.Path]::GetTempFileName()
        try {
            [System.IO.File]::WriteAllText($tempFile, $body, (New-Object System.Text.UTF8Encoding $false))

            $createOut = gh issue create `
                --repo $Repo `
                --title $title `
                --body-file $tempFile `
                --label "type:user-story,status:ready-for-architect,origin:backlog-triage" `
                2>&1

            if ($LASTEXITCODE -ne 0) {
                Write-Log "Failed to create issue '$title': $createOut" "ERROR"
                continue
            }

            $createdUrl = ConvertTo-SafeString $createOut
            $createdNum = ($createdUrl.Trim() -split "/")[-1]
            Write-Log "Created story #$createdNum ($createdUrl)."

            foreach ($absorbedNum in $absorbed) {
                Write-Log "Closing absorbed issue #$absorbedNum..."
                $closeComment = "Closed as absorbed and consolidated into parent story #$createdNum."
                $null = gh issue comment $absorbedNum --repo $Repo --body $closeComment 2>&1
                $null = gh issue close $absorbedNum --repo $Repo 2>&1
            }
        } finally {
            if (Test-Path -LiteralPath $tempFile) {
                Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# --- Main Flow ---
Write-Log "======================================================="
Write-Log " [Backlog Triage] Starting local pipeline run ($Repo)"
Write-Log "======================================================="

Sync-Checkout

$anyFound = $false
foreach ($label in $Labels) {
    $issues = Get-OpenIssuesForLabel -Label $label
    if ($issues.Count -gt 0) {
        $anyFound = $true
        Run-TriageForLabel -Label $label -Issues $issues
    }
}

if (-not $anyFound) {
    Write-Log "No open backlog issues found across labels ($($Labels -join ', ')). Exiting clean."
}

Write-Log "Backlog triage run completed."
