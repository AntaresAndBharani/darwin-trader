<#
.SYNOPSIS
    Local Windows Task Scheduler replacement for the GitHub Actions
    "Architect" workflow -- Fetch -> Gate -> Judge -> Act, judgment-only
    LLM call.

.DESCRIPTION
    Design: ws-setups/graph-engineering/docs/definition-node.md

    Runs the same batch decomposition procedure as
    `.github/workflows/architect.yml` / `.claude/tasks/architect-*.md`,
    but splits it so the LLM is only ever asked to do the one thing that
    genuinely needs judgment (decomposing/restructuring/clarifying a story's
    subtask set), while every deterministic step (listing stories, reading
    their context and existing subtasks, creating/updating/closing subtask
    issues, posting comments, labeling, syncing the checkout) runs as plain
    PowerShell/gh:

      1. Fetch  - one `gh issue list` call per trigger label (never
                  combined -- `gh issue list --label a,b,c` is AND
                  semantics, not OR, so each of the three status labels
                  needs its own call to find issues matching ANY of
                  them), filtered to only `type:user-story` issues.
                  For each qualifying story, `gh issue view` for full context
                  and `gh api .../sub_issues` for its existing subtasks.
      2. Gate   - if no open issue matches any of the three trigger labels,
                  exit 0 without ever invoking claude.exe. A poll with nothing
                  to do must cost zero LLM tokens.
      3. Judge  - one short `claude.exe --print` call per qualifying
                  story, using the judgment prompt template matching its mode
                  (`.claude/tasks/architect-decompose.md`, `architect-restructure.md`,
                  or `architect-answer-clarifications.md`). Read-only tools
                  (`--tools "Read,Grep,Glob"`) with `-WorkingDirectory` pinned to
                  the repo root.
      4. Act    - apply the decision: on PO_ESCALATION, swap the trigger label
                  for `status:needs-po-input` and post the conflict as a comment;
                  on PROCEED, create/update/close subtask issues (linking new
                  ones via the GitHub Sub-issues API), post summary comment,
                  and swap the trigger label for `status:review`.

.EXAMPLE
    .\scripts\local-pipeline\run-architect.ps1
#>
param(
    [string]$Repo = "AntaresAndBharani/darwin-trader",
    [string]$ClaudePath = "C:\Users\rogal\.local\bin\claude.exe",
    [string]$DefaultModel = "claude-sonnet-5",
    [string]$BacklogTriageModel = "claude-sonnet-5",
    [string]$Effort = "medium",
    [string]$PromptTemplateDir = (Join-Path $PSScriptRoot "..\..\.claude\tasks"),
    [int[]]$OnlyIssueNumbers = @()
)

$ErrorActionPreference = "Stop"

$TriggerLabels = @("status:ready-for-architect", "status:needs-revision", "status:needs-clarification")
$ModeByTriggerLabel = @{
    "status:ready-for-architect" = "decompose"
    "status:needs-revision"      = "restructure"
    "status:needs-clarification" = "answer_clarifications"
}
$PromptFileByMode = @{
    "decompose"             = "architect-decompose.md"
    "restructure"           = "architect-restructure.md"
    "answer_clarifications" = "architect-answer-clarifications.md"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $RepoRoot "logs\local-pipeline"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir ("architect-{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

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

function Get-OpenStoriesForLabel {
    param([string]$TriggerLabel)

    $raw = $null
    try {
        $raw = gh issue list --repo $Repo --label $TriggerLabel --state open --json number,title,body,labels 2>&1
    } catch {
        Write-Log "gh issue list threw for trigger label '$TriggerLabel': $_" "ERROR"
        throw
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh issue list exited $LASTEXITCODE for '$TriggerLabel': $(ConvertTo-SafeString $raw)" "ERROR"
        throw "gh issue list failed for $TriggerLabel"
    }

    $rawText = ConvertTo-SafeString $raw
    if ([string]::IsNullOrWhiteSpace($rawText)) { return @() }

    $parsed = $null
    try {
        $parsed = $rawText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed to parse JSON for label '$TriggerLabel': $_. Raw: $rawText" "ERROR"
        throw
    }

    $matchingStories = @()
    if ($null -ne $parsed) {
        foreach ($item in @($parsed)) {
            if ($null -eq $item) { continue }
            $isStory = $false
            if ($null -ne $item.labels) {
                foreach ($lbl in @($item.labels)) {
                    if ($null -ne $lbl -and $lbl.name -eq "type:user-story") {
                        $isStory = $true
                        break
                    }
                }
            }
            if ($isStory) {
                $matchingStories += $item
            }
        }
    }

    return , $matchingStories
}

function Get-StoryFullContext {
    param([int]$IssueNumber)

    $raw = $null
    try {
        $raw = gh issue view $IssueNumber --repo $Repo --json number,title,body,labels,comments 2>&1
    } catch {
        Write-Log "gh issue view threw for story #${IssueNumber}: $_" "ERROR"
        throw
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh issue view exited $LASTEXITCODE for story #${IssueNumber}: $(ConvertTo-SafeString $raw)" "ERROR"
        throw "gh issue view failed for story #$IssueNumber"
    }

    $rawText = ConvertTo-SafeString $raw
    if ([string]::IsNullOrWhiteSpace($rawText)) {
        throw "gh issue view returned empty text for story #$IssueNumber"
    }

    return ($rawText | ConvertFrom-Json -ErrorAction Stop)
}

function Get-ExistingSubtasks {
    param([int]$StoryNumber)

    $raw = $null
    try {
        $raw = gh api "repos/$Repo/issues/$StoryNumber/sub_issues" -q '[.[] | select(.state=="open")] | .[].number' 2>&1
    } catch {
        Write-Log "gh api sub_issues threw for story #${StoryNumber}: $_" "WARN"
        return @()
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gh api sub_issues exited $LASTEXITCODE for story #${StoryNumber}: $(ConvertTo-SafeString $raw)" "WARN"
        return @()
    }

    $rawText = ConvertTo-SafeString $raw
    if ([string]::IsNullOrWhiteSpace($rawText)) { return @() }

    $subtaskNumbers = @()
    foreach ($line in ($rawText -split '\r?\n')) {
        $trimmed = $line.Trim()
        if ($trimmed -match '^\d+$') {
            $subtaskNumbers += [int]$trimmed
        }
    }

    $subtasks = @()
    foreach ($subNum in $subtaskNumbers) {
        try {
            $subRaw = gh issue view $subNum --repo $Repo --json number,title,body,labels,comments 2>&1
            if ($LASTEXITCODE -eq 0) {
                $subText = ConvertTo-SafeString $subRaw
                if (-not [string]::IsNullOrWhiteSpace($subText)) {
                    $subtasks += ($subText | ConvertFrom-Json -ErrorAction Stop)
                }
            }
        } catch {
            Write-Log "Failed to fetch subtask #${subNum}: $_" "WARN"
        }
    }

    return , $subtasks
}

function Invoke-ArchitectJudge {
    param(
        [pscustomobject]$StoryObj,
        [array]$ExistingSubtasks,
        [string]$Mode,
        [string]$Model
    )

    $issueNumber = $StoryObj.number
    $promptFile = $PromptFileByMode[$Mode]
    $promptPath = Join-Path $PromptTemplateDir $promptFile

    if (-not (Test-Path -LiteralPath $promptPath)) {
        Write-Log "Prompt template not found at '$promptPath'" "ERROR"
        return $null
    }

    $template = Get-Content -LiteralPath $promptPath -Raw -Encoding utf8

    $commentsJson = "[]"
    if ($null -ne $StoryObj.comments) {
        $commentsJson = ($StoryObj.comments | ConvertTo-Json -Depth 5)
    }

    $subtasksJson = "[]"
    if ($ExistingSubtasks.Count -gt 0) {
        $subtasksJson = ($ExistingSubtasks | ConvertTo-Json -Depth 5)
    }

    $prompt = $template.
        Replace('{{ISSUE_NUMBER}}', [string]$issueNumber).
        Replace('{{ISSUE_TITLE}}', [string]$StoryObj.title).
        Replace('{{ISSUE_BODY}}', [string]$StoryObj.body).
        Replace('{{ISSUE_COMMENTS_JSON}}', $commentsJson).
        Replace('{{EXISTING_SUBTASKS_JSON}}', $subtasksJson)

    Write-Log "Invoking claude.exe (model=$Model, mode=$Mode, effort=$Effort, tools=Read,Grep,Glob) for story #$issueNumber..."

    $result = $null
    try {
        $args = @(
            "--model", $Model,
            "--effort", $Effort,
            "--output-format", "json",
            "--tools", "Read,Grep,Glob",
            "--permission-mode", "dontAsk",
            "--print", $prompt
        )
        $result = Invoke-NativeProcess -FilePath $ClaudePath -ArgumentStrings $args -WorkingDirectory $RepoRoot
    } catch {
        Write-Log "claude.exe invocation threw for story #${issueNumber}: $_" "ERROR"
        return $null
    }

    if ($result.ExitCode -ne 0) {
        Write-Log "claude.exe exited $($result.ExitCode) for story #${issueNumber}. StdOut: $($result.StdOut) StdErr: $($result.StdErr)" "ERROR"
        return $null
    }

    $claudeRawText = $result.StdOut.Trim()
    $envelope = $null
    try {
        $envelope = $claudeRawText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed to parse claude.exe JSON envelope for story #${issueNumber}: $_. Raw: $claudeRawText" "ERROR"
        return $null
    }

    if ($envelope.is_error -eq $true) {
        Write-Log "claude.exe reported is_error=true for story #${issueNumber}. Envelope: $claudeRawText" "ERROR"
        return $null
    }

    if ([string]::IsNullOrWhiteSpace($envelope.result)) {
        Write-Log "claude.exe envelope for story #$issueNumber had an empty 'result' field." "ERROR"
        return $null
    }

    $responseText = $envelope.result.Trim()
    if ($responseText -match '(?s)```(?:json)?\s*(.*?)\s*```') {
        $responseText = $Matches[1].Trim()
    }

    Write-Log "Judge raw response for story #${issueNumber}: $responseText"

    $decisionObj = $null
    try {
        $decisionObj = $responseText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed to parse decision JSON for story #${issueNumber}: $_. Response: $responseText" "ERROR"
        return $null
    }

    if ($decisionObj.outcome -ne "PROCEED" -and $decisionObj.outcome -ne "PO_ESCALATION") {
        Write-Log "Judge returned unexpected outcome '$($decisionObj.outcome)' for story #${issueNumber}." "ERROR"
        return $null
    }

    return $decisionObj
}

function Apply-ArchitectDecision {
    param(
        [int]$StoryNumber,
        [string]$TriggerLabel,
        [pscustomobject]$DecisionObj
    )

    $outcome = $DecisionObj.outcome
    Write-Log "Applying Architect decision '$outcome' for story #$StoryNumber (trigger was '$TriggerLabel')..."

    if ($outcome -eq "PO_ESCALATION") {
        $conflict = $DecisionObj.conflict
        if ([string]::IsNullOrWhiteSpace($conflict)) {
            $conflict = "Architect encountered an architectural conflict requiring Product Owner decision."
        }

        $body = "**Architect escalation:**`n`n$conflict"
        $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "architect-escalation-$([guid]::NewGuid()).md"
        try {
            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($bodyFile, $body, $utf8NoBom)

            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                $null = gh issue comment $StoryNumber --repo $Repo --body-file $bodyFile 2>&1
                $null = gh issue edit $StoryNumber --repo $Repo --remove-label $TriggerLabel 2>&1
                $null = gh issue edit $StoryNumber --repo $Repo --add-label "status:needs-po-input" 2>&1
            } finally {
                $ErrorActionPreference = $prevEAP
            }
        } finally {
            Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
        }

        Write-Log "Story #$StoryNumber escalated to PO (status:needs-po-input)."
        return
    }

    # outcome == "PROCEED"
    $subtasksObj = $DecisionObj.subtasks
    $createdCount = 0
    $updatedCount = 0
    $closedCount = 0

    if ($null -ne $subtasksObj) {
        # 1. Closes
        if ($null -ne $subtasksObj.close) {
            foreach ($closeItem in @($subtasksObj.close)) {
                if ($null -eq $closeItem) { continue }
                $subNum = $closeItem.subtask_number
                $reason = $closeItem.reason
                if ($subNum -gt 0) {
                    Write-Log "Closing subtask #${subNum} (reason: $reason)..."
                    $closeComment = "Closed by Architect: $reason"
                    $null = gh issue comment $subNum --repo $Repo --body $closeComment 2>&1
                    $null = gh issue close $subNum --repo $Repo 2>&1
                    $closedCount++
                }
            }
        }

        # 2. Updates
        if ($null -ne $subtasksObj.update) {
            foreach ($updateItem in @($subtasksObj.update)) {
                if ($null -eq $updateItem) { continue }
                $subNum = $updateItem.subtask_number
                if ($subNum -gt 0) {
                    Write-Log "Updating subtask #${subNum}..."
                    $bodyLines = @(
                        "### Task description",
                        [string]$updateItem.task_description,
                        "",
                        "### Files / entry points",
                        [string]$updateItem.entry_points,
                        "",
                        "### Acceptance criteria"
                    )
                    if ($null -ne $updateItem.acceptance_criteria) {
                        foreach ($ac in @($updateItem.acceptance_criteria)) {
                            $bodyLines += "- [ ] $ac"
                        }
                    }
                    $bodyLines += @(
                        "",
                        "### How to verify",
                        [string]$updateItem.verification
                    )

                    $bodyContent = ($bodyLines -join "`n")
                    $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "subtask-update-$([guid]::NewGuid()).md"
                    try {
                        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
                        [System.IO.File]::WriteAllText($bodyFile, $bodyContent, $utf8NoBom)
                        $null = gh issue edit $subNum --repo $Repo --body-file $bodyFile 2>&1
                        $updatedCount++
                    } finally {
                        Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
                    }
                }
            }
        }

        # 3. Creates
        if ($null -ne $subtasksObj.create) {
            foreach ($createItem in @($subtasksObj.create)) {
                if ($null -eq $createItem) { continue }
                $title = [string]$createItem.title
                if (-not $title.StartsWith("[Subtask]:")) {
                    $title = "[Subtask]: $title"
                }

                $bodyLines = @(
                    "### Task description",
                    [string]$createItem.task_description,
                    "",
                    "### Files / entry points",
                    [string]$createItem.entry_points,
                    "",
                    "### Acceptance criteria"
                )
                if ($null -ne $createItem.acceptance_criteria) {
                    foreach ($ac in @($createItem.acceptance_criteria)) {
                        $bodyLines += "- [ ] $ac"
                    }
                }
                $bodyLines += @(
                    "",
                    "### How to verify",
                    [string]$createItem.verification
                )

                $bodyContent = ($bodyLines -join "`n")
                $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "subtask-create-$([guid]::NewGuid()).md"
                try {
                    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
                    [System.IO.File]::WriteAllText($bodyFile, $bodyContent, $utf8NoBom)

                    $prevEAP = $ErrorActionPreference
                    $ErrorActionPreference = "Continue"
                    try {
                        $createOut = gh issue create `
                            --repo $Repo `
                            --title $title `
                            --body-file $bodyFile `
                            --label "type:subtask,status:review" `
                            2>&1

                        if ($LASTEXITCODE -eq 0) {
                            $createdUrl = ConvertTo-SafeString $createOut
                            $createdNum = ($createdUrl.Trim() -split "/")[-1]
                            Write-Log "Created subtask #$createdNum ($createdUrl); linking as sub_issue to story #$StoryNumber..."

                            $dbIdOut = gh api "repos/$Repo/issues/$createdNum" -q .id 2>&1
                            $dbId = (ConvertTo-SafeString $dbIdOut).Trim()
                            $linkOut = gh api --method POST "repos/$Repo/issues/$StoryNumber/sub_issues" -F "sub_issue_id=$dbId" 2>&1
                            if ($LASTEXITCODE -ne 0) {
                                Write-Log "Failed to link subtask #${createdNum} to story #${StoryNumber}: $(ConvertTo-SafeString $linkOut)" "WARN"
                            } else {
                                Write-Log "Subtask #${createdNum} linked successfully."
                            }
                            $createdCount++
                        } else {
                            Write-Log "Failed to create subtask '$title': $(ConvertTo-SafeString $createOut)" "ERROR"
                        }
                    } finally {
                        $ErrorActionPreference = $prevEAP
                    }
                } finally {
                    Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }

    # Summary Comment & Relabel to status:review
    $summaryComment = "<!-- architect-summary -->`n**Architect batch decomposition complete.**`n`n" +
                      "- Subtasks created: $createdCount`n" +
                      "- Subtasks updated: $updatedCount`n" +
                      "- Subtasks closed: $closedCount`n`n" +
                      "Handing over to Three Amigos for batch readiness review."

    $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "architect-summary-$([guid]::NewGuid()).md"
    try {
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($bodyFile, $summaryComment, $utf8NoBom)

        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $null = gh issue comment $StoryNumber --repo $Repo --body-file $bodyFile 2>&1
            $null = gh issue edit $StoryNumber --repo $Repo --remove-label $TriggerLabel 2>&1
            $null = gh issue edit $StoryNumber --repo $Repo --add-label "status:review" 2>&1
        } finally {
            $ErrorActionPreference = $prevEAP
        }
    } finally {
        Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
    }

    Write-Log "Story #$StoryNumber relabeled to status:review (handing over to Three Amigos)."
}

# --- Main ---
try {
    Write-Log "===== Architect local run starting ($Repo) ====="

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

    $eligibleStories = @()
    foreach ($trigger in $TriggerLabels) {
        $stories = Get-OpenStoriesForLabel -TriggerLabel $trigger
        foreach ($st in $stories) {
            if ($OnlyIssueNumbers.Count -gt 0 -and ($OnlyIssueNumbers -notcontains $st.number)) {
                continue
            }
            $eligibleStories += [pscustomobject]@{
                Number       = $st.number
                TriggerLabel = $trigger
                Mode         = $ModeByTriggerLabel[$trigger]
            }
        }
    }

    if ($eligibleStories.Count -eq 0) {
        Write-Log "No open user stories matching trigger labels ($($TriggerLabels -join ', ')). Exiting clean."
        Write-Log "===== Architect local run complete (no-op) ====="
        exit 0
    }

    Write-Log "Discovered $($eligibleStories.Count) eligible story/stories to process."

    if (-not (Test-Path -LiteralPath $ClaudePath)) {
        Write-Log "claude.exe not found at '$ClaudePath'." "ERROR"
        exit 1
    }

    foreach ($item in $eligibleStories) {
        $storyNum = $item.Number
        $trigger = $item.TriggerLabel
        $mode = $item.Mode

        Write-Log "Processing story #$storyNum in mode '$mode' (trigger: $trigger)..."

        $storyObj = Get-StoryFullContext -IssueNumber $storyNum
        $existingSubtasks = Get-ExistingSubtasks -StoryNumber $storyNum

        $modelToUse = $DefaultModel
        if ($null -ne $storyObj.labels) {
            foreach ($lbl in @($storyObj.labels)) {
                if ($null -ne $lbl -and $lbl.name -eq "origin:backlog-triage") {
                    $modelToUse = $BacklogTriageModel
                    break
                }
            }
        }

        $decision = Invoke-ArchitectJudge -StoryObj $storyObj -ExistingSubtasks $existingSubtasks -Mode $mode -Model $modelToUse
        if ($null -eq $decision) {
            Write-Log "Judge failed for story #$storyNum. Skipping." "WARN"
            continue
        }

        Apply-ArchitectDecision -StoryNumber $storyNum -TriggerLabel $trigger -DecisionObj $decision
    }

    Write-Log "===== Architect local run complete ====="
    exit 0
} catch {
    Write-Log "Unhandled error in Architect run: $_" "ERROR"
    exit 1
}
