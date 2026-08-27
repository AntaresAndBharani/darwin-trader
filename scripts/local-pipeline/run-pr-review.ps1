<#
.SYNOPSIS
    Local Windows Task Scheduler replacement for the GitHub Actions "PR
    Review" workflow -- Fetch -> Gate -> Judge -> Act, judgment-only LLM call.

.DESCRIPTION
    Design: ws-setups/graph-engineering/docs/pr-review-node.md

    Runs the same review procedure as `.github/workflows/pr-review.yml` /
    `.claude/tasks/pr-review.md`, but splits it so the LLM is only ever
    asked to do the one thing that genuinely needs judgment (the review
    itself), while every deterministic step (listing PRs, reading comments/diffs,
    round-cap counting, posting comments, labeling, filing follow-up issues,
    syncing the checkout) runs as plain PowerShell/gh:

      1. Fetch  - `gh pr list` for open PRs; per PR, `gh pr diff`,
                  `gh pr view --json comments`, and (if the PR body links
                  one) `gh issue view` for the linked issue.
      2. Gate   - skip a PR entirely (no LLM call) if it has already hit
                  the CHANGES_REQUESTED round cap (posting a one-time
                  escalation comment the first time that happens), or if
                  its most recent verdict comment already covers the PR's
                  current HEAD commit. If every open PR is skipped this
                  way, exit 0 without ever invoking claude.exe. A poll with
                  nothing to do must cost zero LLM tokens.
      3. Judge  - one short `claude.exe --print` call per PR that needs
                  review, using the judgment-only prompt template at
                  `.claude/tasks/pr-review.md`. No tool/bash access (`--tools ""`) --
                  the model only ever sees PR/issue text embedded in the
                  prompt and returns a JSON verdict.
      4. Act    - post the verdict as a PR comment (embedding the reviewed
                  commit's SHA so the gate above can detect "already
                  reviewed at this HEAD" on the next poll), swap the
                  `review:approved` / `review:changes-requested` label,
                  and file any follow-up backlog issues the judge flagged.

.EXAMPLE
    .\scripts\local-pipeline\run-pr-review.ps1
#>
param(
    [string]$Repo = "AntaresAndBharani/darwin-trader",
    [string]$ClaudePath = "C:\Users\rogal\.local\bin\claude.exe",
    [string]$Model = "claude-sonnet-5",
    [int]$RoundCap = 3,
    [string]$PromptTemplatePath = (Join-Path $PSScriptRoot "..\..\.claude\tasks\pr-review.md")
)

$ErrorActionPreference = "Stop"

$VerdictMarker = "<!-- pr-review-verdict -->"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs\local-pipeline"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir ("pr-review-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

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

function ConvertTo-SafeString {
    param($InputObject)
    if ($null -eq $InputObject) { return "" }
    if ($InputObject -is [array]) {
        return (($InputObject -join "`n")).Trim()
    }
    return ([string]$InputObject).Trim()
}

function Invoke-NativeProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentStrings,
        [string]$StandardInput = $null
    )

    $argLine = ($ArgumentStrings | ForEach-Object { ConvertTo-EscapedArgument $_ }) -join ' '

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $argLine
    if ($null -ne $StandardInput) {
        $psi.RedirectStandardInput = $true
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($null -ne $StandardInput) {
        $utf8Writer = New-Object System.IO.StreamWriter($proc.StandardInput.BaseStream, [System.Text.Encoding]::UTF8)
        $utf8Writer.Write($StandardInput)
        $utf8Writer.Flush()
        $utf8Writer.Close()
    }
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $proc.ExitCode
        StdOut   = $stdout
        StdErr   = $stderr
    }
}

function Get-OpenPullRequests {
    Write-Log "Fetching open pull requests..."
    $raw = $null
    try {
        $raw = gh pr list --repo $Repo --state open --json number,title,body,headRefName,headRefOid 2>&1
    } catch {
        Write-Log "gh pr list threw: $_" "ERROR"
        throw
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh pr list exited $LASTEXITCODE`: $(ConvertTo-SafeString $raw)" "ERROR"
        throw "gh pr list failed"
    }

    $prs = @()
    $rawText = ConvertTo-SafeString $raw
    if (-not [string]::IsNullOrWhiteSpace($rawText)) {
        try {
            $parsed = $rawText | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Log "Failed to parse gh pr list JSON: $_. Raw: $rawText" "ERROR"
            throw
        }
        if ($null -ne $parsed) {
            foreach ($item in @($parsed)) {
                if ($null -ne $item) { $prs += $item }
            }
        }
    }

    Write-Log "Fetched $($prs.Count) open pull request(s)."
    return , $prs
}

function Get-PRComments {
    param([int]$Number)

    $raw = $null
    try {
        $raw = gh pr view $Number --repo $Repo --json comments 2>&1
    } catch {
        Write-Log "gh pr view (comments) threw for PR #${Number}: $_" "ERROR"
        throw
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh pr view (comments) exited $LASTEXITCODE for PR #${Number}: $(ConvertTo-SafeString $raw)" "ERROR"
        throw "gh pr view --json comments failed for PR #$Number"
    }

    $comments = @()
    $rawText = ConvertTo-SafeString $raw
    if (-not [string]::IsNullOrWhiteSpace($rawText)) {
        try {
            $parsed = $rawText | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Log "Failed to parse gh pr view comments JSON for PR #${Number}: $_. Raw: $rawText" "ERROR"
            throw
        }
        if ($null -ne $parsed.comments) {
            foreach ($item in @($parsed.comments)) {
                if ($null -ne $item) { $comments += $item }
            }
        }
    }
    return , $comments
}

function Get-PRDiff {
    param([int]$Number)

    $raw = $null
    try {
        $raw = gh pr diff $Number --repo $Repo 2>&1
    } catch {
        Write-Log "gh pr diff threw for PR #${Number}: $_" "ERROR"
        throw
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh pr diff exited $LASTEXITCODE for PR #${Number}: $(ConvertTo-SafeString $raw)" "ERROR"
        throw "gh pr diff failed for PR #$Number"
    }
    return ConvertTo-SafeString $raw
}

function Get-LinkedIssueJson {
    param(
        [string]$Body,
        [int]$PrNumber
    )

    if ([string]::IsNullOrWhiteSpace($Body)) { return $null }
    if ($Body -notmatch '(?i)(close[sd]?|fixe?[sd]?|resolve[sd]?)\s*:?\s*#(\d+)') {
        return $null
    }
    $issueNumber = $Matches[2]

    Write-Log "PR #$PrNumber links issue #$issueNumber; fetching its details..."
    $raw = $null
    try {
        $raw = gh issue view $issueNumber --repo $Repo --json number,title,body 2>&1
    } catch {
        Write-Log "gh issue view threw for linked issue #${issueNumber}: $_. Continuing without linked issue context." "WARN"
        return $null
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh issue view exited $LASTEXITCODE for linked issue #${issueNumber}: $(ConvertTo-SafeString $raw). Continuing without linked issue context." "WARN"
        return $null
    }

    return ConvertTo-SafeString $raw
}

function Get-VerdictComments {
    param([array]$Comments)
    return @($Comments) | Where-Object {
        $null -ne $_ -and $_.body -is [string] -and $_.body.TrimStart().StartsWith($VerdictMarker)
    }
}

function Publish-EscalationComment {
    param([int]$PrNumber)

    $body = "<!-- pr-review-escalated -->`n**PR Review escalation -- round cap reached ($RoundCap):** this PR has gone through $RoundCap review/fix rounds without reaching APPROVED. Not reviewing again automatically -- please look at the history above and decide how to proceed."

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = gh pr comment $PrNumber --repo $Repo --body $body 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Failed to post escalation comment on PR #${PrNumber}: $(ConvertTo-SafeString $output)" "ERROR"
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function Test-PrNeedsReview {
    param([pscustomobject]$Pr)

    $prNumber = $Pr.number
    $comments = Get-PRComments -Number $prNumber
    $verdictComments = Get-VerdictComments -Comments $comments

    $changesRequestedCount = @($verdictComments | Where-Object { $_.body -match 'CHANGES_REQUESTED' }).Count

    if ($changesRequestedCount -ge $RoundCap) {
        $alreadyEscalated = @($comments | Where-Object { $_.body -match '<!-- pr-review-escalated -->' }).Count -gt 0
        if (-not $alreadyEscalated) {
            Write-Log "PR #$prNumber has reached the round cap ($RoundCap CHANGES_REQUESTED verdicts); posting escalation comment."
            Publish-EscalationComment -PrNumber $prNumber
        }
        return [pscustomobject]@{ NeedsReview = $false; Reason = "round cap ($RoundCap) reached" }
    }

    if ($verdictComments.Count -eq 0) {
        return [pscustomobject]@{ NeedsReview = $true; Reason = "no prior verdict comment" }
    }

    $lastVerdictComment = $verdictComments | Select-Object -Last 1
    $lastSha = $null
    if ($lastVerdictComment.body -match '<!-- pr-review-sha:([0-9a-f]+) -->') {
        $lastSha = $Matches[1]
    }

    if ($null -ne $lastSha -and $lastSha -eq $Pr.headRefOid) {
        return [pscustomobject]@{ NeedsReview = $false; Reason = "already reviewed at current HEAD ($lastSha)" }
    }

    return [pscustomobject]@{ NeedsReview = $true; Reason = "new commits since last review (last reviewed sha: $lastSha)" }
}

function Invoke-PrReviewJudge {
    param(
        [int]$PrNumber,
        [string]$PrTitle,
        [string]$PrBody,
        [string]$PrDiff,
        [string]$LinkedIssueJson,
        [string]$PromptTemplate
    )

    $linkedSection = "(no linked issue found)"
    if (-not [string]::IsNullOrWhiteSpace($LinkedIssueJson)) {
        $linkedSection = $LinkedIssueJson
    }

    $prompt = $PromptTemplate.Replace('{{PR_TITLE}}', [string]$PrTitle).Replace('{{PR_BODY}}', [string]$PrBody).Replace('{{PR_DIFF}}', [string]$PrDiff).Replace('{{LINKED_ISSUE_JSON}}', $linkedSection).Replace('{{PR_URL}}', "https://github.com/$Repo/pull/$PrNumber").Replace('{{PR_NUMBER}}', "$PrNumber")

    Write-Log "Invoking claude.exe (model=$Model) for PR #$PrNumber..."
    $result = $null
    try {
        $args = @("--model", $Model, "--effort", "medium", "--output-format", "json", "--tools", "", "-p")
        $result = Invoke-NativeProcess -FilePath $ClaudePath -ArgumentStrings $args -StandardInput $prompt
    } catch {
        Write-Log "claude.exe invocation threw for PR #${PrNumber}: $_" "ERROR"
        return $null
    }
    if ($result.ExitCode -ne 0) {
        Write-Log "claude.exe exited $($result.ExitCode) for PR #${PrNumber}. StdOut: $($result.StdOut) StdErr: $($result.StdErr)" "ERROR"
        return $null
    }

    $claudeRawText = $result.StdOut.Trim()

    $envelope = $null
    try {
        $envelope = $claudeRawText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed to parse claude.exe JSON envelope for PR #${PrNumber}: $_. Raw: $claudeRawText" "ERROR"
        return $null
    }

    if ($envelope.is_error -eq $true) {
        Write-Log "claude.exe reported is_error=true for PR #${PrNumber}. Envelope: $claudeRawText" "ERROR"
        return $null
    }

    if ([string]::IsNullOrWhiteSpace($envelope.result)) {
        Write-Log "claude.exe envelope for PR #$PrNumber had an empty 'result' field." "ERROR"
        return $null
    }

    $responseText = $envelope.result.Trim()
    if ($responseText -match '(?s)```(?:json)?\s*(.*?)\s*```') {
        $responseText = $Matches[1].Trim()
    }
    if ($responseText -match '(?s)(\{.*\})') {
        $responseText = $Matches[1].Trim()
    }

    Write-Log "Judge response for PR #${PrNumber}: $responseText"

    $verdictObj = $null
    try {
        $verdictObj = $responseText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        try {
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = "python"
            $psi.Arguments = "-c `"import json, sys; print(json.dumps(json.loads(sys.stdin.read()))))`""
            $psi.RedirectStandardInput = $true
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError = $true
            $psi.UseShellExecute = $false
            $proc = [System.Diagnostics.Process]::Start($psi)
            $utf8Writer = New-Object System.IO.StreamWriter($proc.StandardInput.BaseStream, [System.Text.Encoding]::UTF8)
            $utf8Writer.Write($responseText)
            $utf8Writer.Flush()
            $utf8Writer.Close()
            $stdout = $proc.StandardOutput.ReadToEnd()
            $proc.WaitForExit()
            if ($proc.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($stdout)) {
                $verdictObj = ($stdout | ConvertFrom-Json -ErrorAction Stop)
            }
        } catch {}
    }

    if ($null -eq $verdictObj) {
        Write-Log "Failed to parse verdict JSON from judge response for PR #${PrNumber}. Response: $responseText" "ERROR"
        return $null
    }

    if ($verdictObj.verdict -ne "APPROVED" -and $verdictObj.verdict -ne "CHANGES_REQUESTED") {
        Write-Log "Judge returned an unexpected verdict '$($verdictObj.verdict)' for PR #${PrNumber}; leaving unreviewed for manual triage." "ERROR"
        return $null
    }

    return $verdictObj
}

function Publish-ReviewVerdict {
    param(
        [int]$PrNumber,
        [string]$HeadSha,
        [pscustomobject]$VerdictObj
    )

    $verdict = $VerdictObj.verdict
    Write-Log "Publishing verdict '$verdict' for PR #$PrNumber (head sha $HeadSha)..."

    $commentBody = @(
        $VerdictMarker,
        "<!-- pr-review-sha:$HeadSha -->",
        "**Verdict: $verdict**",
        "",
        [string]$VerdictObj.pr_comment_markdown
    ) -join "`n"

    $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "pr-review-comment-$([guid]::NewGuid()).md"
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($bodyFile, $commentBody, $utf8NoBom)

        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $commentOutput = gh pr comment $PrNumber --repo $Repo --body-file $bodyFile 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Log "Failed to post review comment on PR #${PrNumber}: $(ConvertTo-SafeString $commentOutput)" "ERROR"
                return
            }
        } finally {
            $ErrorActionPreference = $prevEAP
        }
    } finally {
        Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
    }

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        gh pr edit $PrNumber --repo $Repo --remove-label "review:approved" 2>&1 | Out-Null
        gh pr edit $PrNumber --repo $Repo --remove-label "review:changes-requested" 2>&1 | Out-Null

        $newLabel = "review:changes-requested"
        if ($verdict -eq "APPROVED") { $newLabel = "review:approved" }

        $labelOutput = gh pr edit $PrNumber --repo $Repo --add-label $newLabel 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Failed to add label '$newLabel' to PR #${PrNumber}: $(ConvertTo-SafeString $labelOutput)" "ERROR"
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }

    $followups = @()
    if ($null -ne $VerdictObj.followup_backlog_issues) {
        $followups = @($VerdictObj.followup_backlog_issues) | Where-Object { $null -ne $_ }
    }

    foreach ($followup in $followups) {
        if ([string]::IsNullOrWhiteSpace($followup.title)) {
            Write-Log "Skipping malformed follow-up issue for PR #${PrNumber}: missing title." "WARN"
            continue
        }

        $labels = "enhancement"
        if ($null -ne $followup.labels) {
            $labelList = @($followup.labels) | Where-Object { $null -ne $_ }
            if ($labelList.Count -gt 0) { $labels = $labelList -join "," }
        }

        $followupBody = "$($followup.body)`n`n_Flagged during review of #${PrNumber}, deliberately not blocking it._"
        $followupBodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "pr-review-followup-$([guid]::NewGuid()).md"
        try {
            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($followupBodyFile, $followupBody, $utf8NoBom)

            $createOutput = gh issue create --repo $Repo --title $followup.title --body-file $followupBodyFile --label $labels 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Log "Failed to create follow-up issue '$($followup.title)' for PR #${PrNumber}: $(ConvertTo-SafeString $createOutput)" "WARN"
            } else {
                Write-Log "Created follow-up issue '$($followup.title)' for PR #${PrNumber}: $(ConvertTo-SafeString $createOutput)"
            }
        } finally {
            Remove-Item -LiteralPath $followupBodyFile -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- Main ---
try {
    Write-Log "===== PR review run starting ($Repo) ====="

    Write-Log "Syncing local checkout to origin/main..."
    Push-Location $RepoRoot
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"

        git checkout main 2>&1 | ForEach-Object { Write-Log "git: $_" }
        if ($LASTEXITCODE -ne 0) { throw "git checkout main failed with exit code $LASTEXITCODE" }

        git fetch origin 2>&1 | ForEach-Object { Write-Log "git: $_" }
        if ($LASTEXITCODE -ne 0) { throw "git fetch origin failed with exit code $LASTEXITCODE" }

        git reset --hard origin/main 2>&1 | ForEach-Object { Write-Log "git: $_" }
        if ($LASTEXITCODE -ne 0) { throw "git reset --hard origin/main failed with exit code $LASTEXITCODE" }
    } finally {
        $ErrorActionPreference = $prevEAP
        Pop-Location
    }

    if (-not (Test-Path -LiteralPath $PromptTemplatePath)) {
        Write-Log "Prompt template not found at $PromptTemplatePath" "ERROR"
        exit 1
    }
    $PromptTemplate = Get-Content -LiteralPath $PromptTemplatePath -Raw

    $prs = Get-OpenPullRequests

    if ($prs.Count -eq 0) {
        Write-Log "No open pull requests. Exiting without invoking claude.exe."
        Write-Log "===== PR review run complete (no-op) ====="
        exit 0
    }

    $prsNeedingReview = @()
    foreach ($pr in $prs) {
        $gate = Test-PrNeedsReview -Pr $pr
        if ($gate.NeedsReview) {
            Write-Log "PR #$($pr.number) needs review: $($gate.Reason)"
            $prsNeedingReview += $pr
        } else {
            Write-Log "Skipping PR #$($pr.number): $($gate.Reason)"
        }
    }

    if ($prsNeedingReview.Count -eq 0) {
        Write-Log "Nothing to review across $($prs.Count) open pull request(s). Exiting without invoking claude.exe."
        Write-Log "===== PR review run complete (no-op) ====="
        exit 0
    }

    if (-not (Test-Path -LiteralPath $ClaudePath)) {
        Write-Log "claude.exe not found at $ClaudePath; cannot run judge step." "ERROR"
        exit 1
    }

    foreach ($pr in $prsNeedingReview) {
        $linkedIssueJson = Get-LinkedIssueJson -Body $pr.body -PrNumber $pr.number
        $diff = Get-PRDiff -Number $pr.number

        $verdictObj = Invoke-PrReviewJudge -PrNumber $pr.number -PrTitle $pr.title -PrBody $pr.body -PrDiff $diff -LinkedIssueJson $linkedIssueJson -PromptTemplate $PromptTemplate
        if ($null -eq $verdictObj) {
            Write-Log "Judge failed to produce a usable verdict for PR #$($pr.number); leaving it unreviewed for manual triage." "WARN"
            continue
        }

        Publish-ReviewVerdict -PrNumber $pr.number -HeadSha $pr.headRefOid -VerdictObj $verdictObj
    }

    Write-Log "===== PR review run complete ====="
    exit 0
} catch {
    Write-Log "Unhandled error in PR review run: $_" "ERROR"
    exit 1
}
