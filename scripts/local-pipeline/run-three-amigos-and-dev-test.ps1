<#
.SYNOPSIS
    Local Windows Task Scheduler replacement for the Antigravity
    "Three Amigos + Dev & Test" scheduled task.

.DESCRIPTION
    Design: ws-setups/graph-engineering/docs/three-amigos-node.md,
    ws-setups/graph-engineering/docs/dev-test-node.md

    Unlike the other three migrated nodes, this one is NOT a uniform
    Fetch -> Judge -> Act pipeline throughout -- it mirrors the mixed
    character of the original 5-step Antigravity task:

      Step 1  - Three Amigos batch review. Pure judgment, no git/tool
                access needed (same pattern as Backlog Triage/PR Review) --
                always runs, never stops the chain.
      Step 2  - resolve approved-but-conflicting PRs. Fully deterministic,
                zero LLM involvement: git's own `merge=union` driver
                already resolves the unambiguously-additive case during
                rebase; anything git can't auto-resolve is exactly the
                "needs a human" case. Stops the chain if it finds and
                handles one. Runs both Android and Python test suites.
      Step 3  - fix-up work (PR labeled review:changes-requested).
                Discovery is deterministic (the wrapper finds which PR);
                the actual fix is genuinely agentic -- real file/bash
                access via agy.exe, same as the original design. Stops
                the chain if found.
      Step 4  - is anything else already in flight? Fully deterministic.
                Stops the chain if true.
      Step 5  - new implementation work. Same shape as Step 3: wrapper
                picks the target subtask deterministically, agy.exe does
                the actual agentic implementation work.

    A poll with nothing to do at Step 1 and nothing to do at Steps 2-5
    costs zero LLM tokens for the judgment/discovery parts.

.EXAMPLE
    .\scripts\local-pipeline\run-three-amigos-and-dev-test.ps1
#>
param(
    [string]$Repo = "AntaresAndBharani/darwin-trader",
    [string]$AgyPath = "C:\Users\rogal\AppData\Local\agy\bin\agy.exe",
    [string]$JudgeModel = "gemini-3.7-flash-medium",
    [string]$AgenticModel = "gemini-3.7-flash-medium",
    [string]$PromptTemplateDir = (Join-Path $PSScriptRoot "..\..\.claude\tasks"),
    [string]$AntigravityTaskDir = (Join-Path $PSScriptRoot "..\..\.antigravity\tasks"),
    [switch]$OnlyThreeAmigos
)

$ErrorActionPreference = "Stop"

# Ensure GitHub token is loaded for AntaresAndBharani operations
$SetTokenScript = "C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1"
if (Test-Path -LiteralPath $SetTokenScript) {
    & $SetTokenScript
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs\local-pipeline"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir ("three-amigos-and-dev-test-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
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

function Invoke-NativeProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentStrings,
        [string]$WorkingDirectory = ""
    )

    $argLine = ($ArgumentStrings | ForEach-Object { ConvertTo-EscapedArgument $_ }) -join ' '

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $argLine
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        $psi.WorkingDirectory = $WorkingDirectory
    }

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $proc.ExitCode
        StdOut   = $stdout
        StdErr   = $stderr
    }
}

function ConvertFrom-JsonSafeArray {
    param([string]$JsonText)
    $parsed = $JsonText | ConvertFrom-Json -ErrorAction Stop
    if ($parsed -is [array]) { return $parsed }
    return @($parsed)
}

function ConvertTo-SafeString {
    param($InputObject)
    if ($null -eq $InputObject) { return "" }
    if ($InputObject -is [array]) {
        return (($InputObject -join "`n")).Trim()
    }
    return ([string]$InputObject).Trim()
}

function Invoke-GitCommand {
    param([string[]]$GitArgs)
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & git @GitArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = ConvertTo-SafeString $output }
}

function Invoke-GhCommand {
    param([string[]]$GhArgs)
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & gh @GhArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = ConvertTo-SafeString $output }
}

function Get-Subtasks {
    param([int]$ParentNumber, [switch]$OpenOnly)
    $numsResult = Invoke-GhCommand -GhArgs @("api", "repos/$Repo/issues/$ParentNumber/sub_issues", "-q", ".[].number")
    if ($numsResult.ExitCode -ne 0) {
        Write-Log "Failed to fetch sub_issues for #${ParentNumber}: $($numsResult.Output)" "ERROR"
        return @()
    }
    $nums = @($numsResult.Output -split "`n" | Where-Object { $_ -match '^\d+$' })
    $subtasks = @()
    foreach ($n in $nums) {
        $viewResult = Invoke-GhCommand -GhArgs @("issue", "view", $n, "--repo", $Repo, "--json", "number,title,body,labels,state")
        if ($viewResult.ExitCode -ne 0) {
            Write-Log "Failed to fetch subtask #${n}: $($viewResult.Output)" "ERROR"
            continue
        }
        try {
            $obj = $viewResult.Output | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Log "Failed to parse subtask #${n} JSON: $_" "ERROR"
            continue
        }
        if ($OpenOnly -and $obj.state -ne "OPEN") { continue }
        $subtasks += $obj
    }
    return , $subtasks
}

function Test-HasLabel {
    param($Issue, [string]$LabelName)
    return @($Issue.labels | Where-Object { $_.name -eq $LabelName }).Count -gt 0
}

# =====================================================================
# Step 1 -- Three Amigos batch review (judgment-only, always runs)
# =====================================================================
function Invoke-ThreeAmigosStep {
    Write-Log "--- Step 1: Three Amigos batch review ---"

    $storiesResult = Invoke-GhCommand -GhArgs @("issue", "list", "--repo", $Repo, "--label", "type:user-story,status:review", "--state", "open", "--json", "number,title,body")
    if ($storiesResult.ExitCode -ne 0) {
        Write-Log "Failed to fetch status:review stories: $($storiesResult.Output)" "ERROR"
        return
    }
    $stories = @()
    if (-not [string]::IsNullOrWhiteSpace($storiesResult.Output)) {
        try { $stories = ConvertFrom-JsonSafeArray $storiesResult.Output } catch {
            Write-Log "Failed to parse status:review stories JSON: $_" "ERROR"
            return
        }
    }
    Write-Log "Found $($stories.Count) story/stories at status:review."

    $templatePath = Join-Path $PromptTemplateDir "three-amigos-judge.md"
    if ($stories.Count -gt 0 -and -not (Test-Path -LiteralPath $templatePath)) {
        Write-Log "Prompt template not found at $templatePath" "ERROR"
        return
    }
    $template = if ($stories.Count -gt 0) { Get-Content -LiteralPath $templatePath -Raw } else { $null }

    foreach ($story in $stories) {
        $storyNumber = $story.number
        Write-Log "Processing story #$storyNumber for Three Amigos review..."

        $commentsResult = Invoke-GhCommand -GhArgs @("issue", "view", $storyNumber, "--repo", $Repo, "--json", "comments")
        if ($commentsResult.ExitCode -ne 0) {
            Write-Log "Failed to fetch comments for story #${storyNumber}: $($commentsResult.Output)" "ERROR"
            continue
        }
        $commentsObj = $null
        try { $commentsObj = $commentsResult.Output | ConvertFrom-Json -ErrorAction Stop } catch {
            Write-Log "Failed to parse comments JSON for story #${storyNumber}: $_" "ERROR"
            continue
        }
        $verdictCount = @($commentsObj.comments | Where-Object { $_.body -is [string] -and $_.body.TrimStart().StartsWith("<!-- three-amigos-verdict -->") }).Count

        if ($verdictCount -ge 3) {
            Write-Log "Story #$storyNumber has reached the 3-round cap; escalating instead of reviewing again."
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--remove-label", "status:review") | Out-Null
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--add-label", "status:needs-po-input") | Out-Null
            Invoke-GhCommand -GhArgs @("issue", "comment", $storyNumber, "--repo", $Repo, "--body", "Three Amigos round cap (3) reached without READY -- not reviewing again automatically; please look at the review history above and decide how to proceed.") | Out-Null
            continue
        }

        $subtasks = Get-Subtasks -ParentNumber $storyNumber -OpenOnly
        if ($subtasks.Count -eq 0) {
            Write-Log "Story #$storyNumber has no open subtasks; skipping."
            continue
        }

        $subtasksForPrompt = $subtasks | ForEach-Object { [pscustomobject]@{ number = $_.number; title = $_.title; body = $_.body } }
        $subtasksJson = ($subtasksForPrompt | ConvertTo-Json -Depth 5)
        $prompt = $template.Replace('{{STORY_NUMBER}}', [string]$storyNumber).Replace('{{STORY_TITLE}}', [string]$story.title).Replace('{{STORY_BODY}}', [string]$story.body).Replace('{{SUBTASKS_JSON}}', $subtasksJson)

        Write-Log "Invoking agy.exe (model=$JudgeModel) for Three Amigos review of story #$storyNumber..."
        $result = $null
        try {
            $result = Invoke-NativeProcess -FilePath $AgyPath -ArgumentStrings @("--model", $JudgeModel, "--output-format", "json", "--print", $prompt)
        } catch {
            Write-Log "agy.exe invocation threw for story #${storyNumber}: $_" "ERROR"
            continue
        }
        if ($result.ExitCode -ne 0) {
            Write-Log "agy.exe exited $($result.ExitCode) for story #${storyNumber}. StdErr: $($result.StdErr) | StdOut: $($result.StdOut)" "ERROR"
            continue
        }

        $envelope = $null
        try { $envelope = $result.StdOut.Trim() | ConvertFrom-Json -ErrorAction Stop } catch {
            Write-Log "Failed to parse agy.exe envelope for story #${storyNumber}: $_. Raw: $($result.StdOut)" "ERROR"
            continue
        }
        if ([string]::IsNullOrWhiteSpace($envelope.response)) {
            Write-Log "agy.exe envelope for story #$storyNumber had an empty response." "ERROR"
            continue
        }
        $responseText = $envelope.response.Trim()
        if ($responseText -match '(?s)```(?:json)?\s*(.*?)\s*```') {
            $responseText = $Matches[1].Trim()
        }
        $decision = $null
        try { $decision = $responseText | ConvertFrom-Json -ErrorAction Stop } catch {
            Write-Log "Failed to parse Three Amigos decision JSON for story #${storyNumber}: $_. Response: $responseText" "ERROR"
            continue
        }

        $verdict = $decision.batch_verdict
        Write-Log "Three Amigos batch_verdict for story #${storyNumber}: $verdict"

        $commentBody = "<!-- three-amigos-verdict -->`n" + [string]$decision.summary_comment_markdown
        Invoke-GhCommand -GhArgs @("issue", "comment", $storyNumber, "--repo", $Repo, "--body", $commentBody) | Out-Null

        if ($verdict -eq "READY") {
            foreach ($sr in @($decision.subtask_reviews)) {
                $stNum = $sr.subtask_number
                foreach ($lbl in @("status:pending-review", "status:review", "status:needs-revision", "status:needs-clarification")) {
                    Invoke-GhCommand -GhArgs @("issue", "edit", $stNum, "--repo", $Repo, "--remove-label", $lbl) | Out-Null
                }
                Invoke-GhCommand -GhArgs @("issue", "edit", $stNum, "--repo", $Repo, "--add-label", "status:awaiting-approval") | Out-Null
            }
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--remove-label", "status:review") | Out-Null
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--add-label", "status:ready") | Out-Null
        } elseif ($verdict -eq "NEEDS_REVISION") {
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--remove-label", "status:review") | Out-Null
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--add-label", "status:needs-revision") | Out-Null
        } elseif ($verdict -eq "NEEDS_CLARIFICATION") {
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--remove-label", "status:review") | Out-Null
            Invoke-GhCommand -GhArgs @("issue", "edit", $storyNumber, "--repo", $Repo, "--add-label", "status:needs-clarification") | Out-Null
        } else {
            Write-Log "Unexpected batch_verdict '$verdict' for story #${storyNumber}; leaving labels untouched for manual triage." "WARN"
        }
    }
}

# =====================================================================
# Step 2 -- resolve approved-but-conflicting PRs (fully deterministic)
# =====================================================================
function Invoke-ConflictResolutionStep {
    Write-Log "--- Step 2: approved-but-conflicting PR check ---"

    $prsResult = Invoke-GhCommand -GhArgs @("pr", "list", "--repo", $Repo, "--label", "review:approved", "--state", "open", "--json", "number,headRefName,mergeable,body")
    if ($prsResult.ExitCode -ne 0) { return $false }
    $prs = @()
    if (-not [string]::IsNullOrWhiteSpace($prsResult.Output)) {
        try { $prs = ConvertFrom-JsonSafeArray $prsResult.Output } catch { return $false }
    }
    $conflicting = $prs | Where-Object { $_.mergeable -eq "CONFLICTING" } | Select-Object -First 1
    if ($null -eq $conflicting) {
        Write-Log "No approved-but-conflicting PR found."
        return $false
    }

    $prNumber = $conflicting.number
    $branch = $conflicting.headRefName
    $subtaskNumber = $null
    if ($conflicting.body -match '(?i)(close[sd]?|fixe?[sd]?|resolve[sd]?)\s*:?\s*#(\d+)') {
        $subtaskNumber = $Matches[2]
    }
    Write-Log "Found approved-but-conflicting PR #$prNumber (branch $branch, subtask #$subtaskNumber) -- resolving."

    $checkout = Invoke-GitCommand -GitArgs @("checkout", $branch)
    if ($checkout.ExitCode -ne 0) {
        Write-Log "Failed to checkout branch ${branch}: $($checkout.Output)" "ERROR"
        return $true
    }
    Invoke-GitCommand -GitArgs @("fetch", "origin") | Out-Null
    $rebase = Invoke-GitCommand -GitArgs @("rebase", "origin/main")

    if ($rebase.ExitCode -ne 0) {
        Write-Log "Rebase of PR #$prNumber produced a real conflict git could not auto-resolve -- escalating. Output: $($rebase.Output)"
        Invoke-GitCommand -GitArgs @("rebase", "--abort") | Out-Null
        Invoke-GhCommand -GhArgs @("pr", "comment", $prNumber, "--repo", $Repo, "--body", "Automated rebase onto main hit a real conflict that needs a human decision (not an unambiguously-additive case `.gitattributes`'s `merge=union` could resolve on its own). Left the branch as-is -- please resolve manually.") | Out-Null
        if ($subtaskNumber) { Invoke-GhCommand -GhArgs @("issue", "edit", $subtaskNumber, "--repo", $Repo, "--add-label", "status:needs-po-input") | Out-Null }
        Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
        return $true
    }

    Write-Log "Rebase of PR #$prNumber completed cleanly. Re-running test suites before pushing."

    # Android unit tests
    $androidGradle = Join-Path $RepoRoot "android\gradlew.bat"
    $androidDir = Join-Path $RepoRoot "android"
    $androidTests = Invoke-NativeProcess -FilePath $androidGradle -ArgumentStrings @("testSnapshotDebugUnitTest", "--no-daemon") -WorkingDirectory $androidDir

    # Python backend tests
    $pythonTests = Invoke-NativeProcess -FilePath "python.exe" -ArgumentStrings @("-m", "pytest", "api_gateway/tests", "strategy_engine/tests") -WorkingDirectory $RepoRoot

    if ($androidTests.ExitCode -ne 0 -or $pythonTests.ExitCode -ne 0) {
        Write-Log "Tests failed after rebase for PR #$prNumber (Android: $($androidTests.ExitCode), Python: $($pythonTests.ExitCode)). Escalating rather than pushing a broken branch."
        Invoke-GhCommand -GhArgs @("pr", "comment", $prNumber, "--repo", $Repo, "--body", "Rebased onto main cleanly, but the test suite fails on the rebased branch -- this needs a human look, not an automated push. Left the branch as rebased locally; origin unchanged.") | Out-Null
        if ($subtaskNumber) { Invoke-GhCommand -GhArgs @("issue", "edit", $subtaskNumber, "--repo", $Repo, "--add-label", "status:needs-po-input") | Out-Null }
        Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
        return $true
    }

    Invoke-GitCommand -GitArgs @("fetch", "origin") | Out-Null
    $shaResult = Invoke-GitCommand -GitArgs @("rev-parse", "origin/$branch")
    $remoteSha = $shaResult.Output.Trim()
    $push = Invoke-GitCommand -GitArgs @("push", "--force-with-lease=${branch}:${remoteSha}", "origin", $branch)
    if ($push.ExitCode -ne 0) {
        Write-Log "Push failed for PR #${prNumber}: $($push.Output)" "ERROR"
    } else {
        Write-Log "Successfully rebased and pushed PR #$prNumber. This re-triggers PR Review via the SHA-marker mechanism."
    }
    Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
    return $true
}

# =====================================================================
# Step 3 -- fix-up work (deterministic discovery, agentic execution)
# =====================================================================
function Invoke-FixupStep {
    Write-Log "--- Step 3: fix-up (review:changes-requested) check ---"

    $prsResult = Invoke-GhCommand -GhArgs @("pr", "list", "--repo", $Repo, "--label", "review:changes-requested", "--state", "open", "--json", "number,title,headRefName,body")
    if ($prsResult.ExitCode -ne 0) { return $false }
    $prs = @()
    if (-not [string]::IsNullOrWhiteSpace($prsResult.Output)) {
        try { $prs = ConvertFrom-JsonSafeArray $prsResult.Output } catch { return $false }
    }
    if ($prs.Count -eq 0) {
        Write-Log "No PR labeled review:changes-requested found."
        return $false
    }

    $pr = $prs | Select-Object -First 1
    $prNumber = $pr.number
    $branch = $pr.headRefName
    Write-Log "Found fix-up target: PR #$prNumber (branch $branch)."

    $linkedStoryNumber = $null
    if ($pr.body -match '(?i)(close[sd]?|fixe?[sd]?|resolve[sd]?)\s*:?\s*#(\d+)') {
        $subtaskNumber = [int]$Matches[2]
        $parentResult = Invoke-GhCommand -GhArgs @("api", "repos/$Repo/issues/$subtaskNumber/parent")
        if ($parentResult.ExitCode -eq 0) {
            try { $linkedStoryNumber = ($parentResult.Output | ConvertFrom-Json -ErrorAction Stop).number } catch {}
        }
    }
    $storyTitle = ""
    $storyBody = ""
    if ($linkedStoryNumber) {
        $storyResult = Invoke-GhCommand -GhArgs @("issue", "view", $linkedStoryNumber, "--repo", $Repo, "--json", "title,body")
        if ($storyResult.ExitCode -eq 0) {
            try { $storyObj = $storyResult.Output | ConvertFrom-Json -ErrorAction Stop; $storyTitle = $storyObj.title; $storyBody = $storyObj.body } catch {}
        }
    }

    $commentsResult = Invoke-GhCommand -GhArgs @("pr", "view", $prNumber, "--repo", $Repo, "--json", "comments")
    $reviewComment = ""
    if ($commentsResult.ExitCode -eq 0) {
        try {
            $commentsObj = $commentsResult.Output | ConvertFrom-Json -ErrorAction Stop
            $verdictComments = @($commentsObj.comments | Where-Object { $_.body -is [string] -and $_.body.Contains("<!-- pr-review-verdict -->") })
            if ($verdictComments.Count -gt 0) { $reviewComment = ($verdictComments | Select-Object -Last 1).body }
        } catch {}
    }

    $checkout = Invoke-GitCommand -GitArgs @("checkout", $branch)
    if ($checkout.ExitCode -ne 0) {
        Write-Log "Failed to checkout branch ${branch} for PR #${prNumber}: $($checkout.Output)" "ERROR"
        return $true
    }

    $templatePath = Join-Path $AntigravityTaskDir "dev-test-fixup.md"
    if (-not (Test-Path -LiteralPath $templatePath)) {
        Write-Log "Prompt template not found at $templatePath" "ERROR"
        Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
        return $true
    }
    $prompt = (Get-Content -LiteralPath $templatePath -Raw).
        Replace('{{BRANCH_NAME}}', $branch).
        Replace('{{PR_NUMBER}}', [string]$prNumber).
        Replace('{{STORY_NUMBER}}', [string]$linkedStoryNumber).
        Replace('{{STORY_TITLE}}', [string]$storyTitle).
        Replace('{{STORY_BODY}}', [string]$storyBody).
        Replace('{{PR_REVIEW_COMMENT}}', [string]$reviewComment)

    Write-Log "Invoking agy.exe (model=$AgenticModel, full tool access) for fix-up on PR #$prNumber..."
    $result = $null
    try {
        $result = Invoke-NativeProcess -FilePath $AgyPath -ArgumentStrings @("--model", $AgenticModel, "--dangerously-skip-permissions", "--print-timeout", "20m0s", "--output-format", "json", "--print", $prompt) -WorkingDirectory $RepoRoot
    } catch {
        Write-Log "agy.exe invocation threw for fix-up on PR #${prNumber}: $_" "ERROR"
    }
    if ($null -ne $result -and $result.ExitCode -ne 0) {
        Write-Log "agy.exe exited $($result.ExitCode) for fix-up on PR #${prNumber}. StdErr: $($result.StdErr) | StdOut: $($result.StdOut)" "ERROR"
    } else {
        Write-Log "Fix-up session for PR #$prNumber completed."
    }
    Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
    return $true
}

# =====================================================================
# Step 4 -- is anything else already in flight? (fully deterministic)
# =====================================================================
function Test-AnythingInFlight {
    Write-Log "--- Step 4: in-flight check ---"

    $prsResult = Invoke-GhCommand -GhArgs @("pr", "list", "--repo", $Repo, "--state", "open", "--json", "number")
    if ($prsResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($prsResult.Output)) {
        try {
            $prs = ConvertFrom-JsonSafeArray $prsResult.Output
            if ($prs.Count -gt 0) {
                Write-Log "$($prs.Count) open PR(s) exist -- something is mid-review or approved-pending-merge. Stopping this poll."
                return $true
            }
        } catch {}
    }

    $inDevResult = Invoke-GhCommand -GhArgs @("issue", "list", "--repo", $Repo, "--label", "status:in-development", "--state", "open", "--json", "number")
    if ($inDevResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($inDevResult.Output)) {
        try {
            $stories = ConvertFrom-JsonSafeArray $inDevResult.Output
            if ($stories.Count -gt 0) {
                Write-Log "$($stories.Count) story/stories already status:in-development. Stopping this poll."
                return $true
            }
        } catch {}
    }

    Write-Log "Nothing in flight."
    return $false
}

# =====================================================================
# Step 5 -- new implementation work (deterministic discovery, agentic execution)
# =====================================================================
function Invoke-ImplementationStep {
    Write-Log "--- Step 5: new implementation check ---"

    $storiesResult = Invoke-GhCommand -GhArgs @("issue", "list", "--repo", $Repo, "--label", "type:user-story,status:ready", "--state", "open", "--json", "number,title,body")
    if ($storiesResult.ExitCode -ne 0) { return }
    $stories = @()
    if (-not [string]::IsNullOrWhiteSpace($storiesResult.Output)) {
        try { $stories = ConvertFrom-JsonSafeArray $storiesResult.Output } catch { return }
    }
    if ($stories.Count -eq 0) {
        Write-Log "No story at status:ready."
        return
    }

    foreach ($story in $stories) {
        $subtasks = Get-Subtasks -ParentNumber $story.number -OpenOnly | Where-Object { Test-HasLabel -Issue $_ -LabelName "status:awaiting-approval" }
        if (@($subtasks).Count -eq 0) { continue }

        Write-Log "Story #$($story.number) has $(@($subtasks).Count) subtask(s) ready to implement. Marking status:in-development."
        Invoke-GhCommand -GhArgs @("issue", "edit", $story.number, "--repo", $Repo, "--add-label", "status:in-development") | Out-Null

        $templatePath = Join-Path $AntigravityTaskDir "dev-test-implement.md"
        if (-not (Test-Path -LiteralPath $templatePath)) {
            Write-Log "Prompt template not found at $templatePath" "ERROR"
            Invoke-GhCommand -GhArgs @("issue", "edit", $story.number, "--repo", $Repo, "--remove-label", "status:in-development") | Out-Null
            return
        }
        $template = Get-Content -LiteralPath $templatePath -Raw

        foreach ($subtask in @($subtasks)) {
            $branch = "feat/issue-$($subtask.number)"
            Write-Log "Implementing subtask #$($subtask.number) on branch $branch..."

            Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
            Invoke-GitCommand -GitArgs @("pull", "origin", "main") | Out-Null
            $branchResult = Invoke-GitCommand -GitArgs @("checkout", "-b", $branch)
            if ($branchResult.ExitCode -ne 0) {
                Write-Log "Failed to create branch ${branch}: $($branchResult.Output)" "ERROR"
                continue
            }

            $prompt = $template.
                Replace('{{BRANCH_NAME}}', $branch).
                Replace('{{SUBTASK_NUMBER}}', [string]$subtask.number).
                Replace('{{STORY_NUMBER}}', [string]$story.number).
                Replace('{{STORY_TITLE}}', [string]$story.title).
                Replace('{{STORY_BODY}}', [string]$story.body).
                Replace('{{SUBTASK_TITLE}}', [string]$subtask.title).
                Replace('{{SUBTASK_BODY}}', [string]$subtask.body)

            Write-Log "Invoking agy.exe (model=$AgenticModel, full tool access) for implementation of subtask #$($subtask.number)..."
            $result = $null
            try {
                $result = Invoke-NativeProcess -FilePath $AgyPath -ArgumentStrings @("--model", $AgenticModel, "--dangerously-skip-permissions", "--print-timeout", "20m0s", "--output-format", "json", "--print", $prompt) -WorkingDirectory $RepoRoot
            } catch {
                Write-Log "agy.exe invocation threw for subtask #$($subtask.number): $_" "ERROR"
            }
            if ($null -ne $result -and $result.ExitCode -ne 0) {
                Write-Log "agy.exe exited $($result.ExitCode) for subtask #$($subtask.number). StdErr: $($result.StdErr) | StdOut: $($result.StdOut)" "ERROR"
            } else {
                Write-Log "Implementation session for subtask #$($subtask.number) completed."
            }
        }

        Invoke-GitCommand -GitArgs @("checkout", "main") | Out-Null
        Write-Log "Clearing status:in-development from story #$($story.number) (unconditional, every subtask found in this poll was attempted)."
        Invoke-GhCommand -GhArgs @("issue", "edit", $story.number, "--repo", $Repo, "--remove-label", "status:in-development") | Out-Null
        return
    }
}

# --- Main ---
try {
    Write-Log "===== Three Amigos + Dev & Test run starting ($Repo) ====="

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

    Push-Location $RepoRoot
    try {
        Invoke-ThreeAmigosStep

        if ($OnlyThreeAmigos) {
            Write-Log "===== Run complete (OnlyThreeAmigos: stopping before Steps 2-5) ====="
            exit 0
        }

        if (Invoke-ConflictResolutionStep) {
            Write-Log "===== Run complete (stopped after Step 2: conflict resolution) ====="
            exit 0
        }
        if (Invoke-FixupStep) {
            Write-Log "===== Run complete (stopped after Step 3: fix-up) ====="
            exit 0
        }
        if (Test-AnythingInFlight) {
            Write-Log "===== Run complete (stopped after Step 4: in-flight check) ====="
            exit 0
        }
        Invoke-ImplementationStep
        Write-Log "===== Run complete (Step 5: implementation) ====="
    } finally {
        Pop-Location
    }
    exit 0
} catch {
    Write-Log "Unhandled error in three-amigos-and-dev-test run: $_" "ERROR"
    exit 1
}
