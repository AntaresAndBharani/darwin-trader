param (
    [string]$SummaryPath,
    [string]$PrNumber = "",
    [string]$Version = ""
)

if ($PrNumber) {
    if ($PrNumber -notmatch '^\d+$') {
        Write-Host "Invalid PR number '$PrNumber'. PR number must be numeric." -ForegroundColor Yellow
        exit 1
    }
} else {
    if ($null -ne (Get-Command gh -ErrorAction SilentlyContinue)) {
        try {
            $PrJson = gh pr view --json number 2>$null | ConvertFrom-Json
            if ($null -ne $PrJson -and $null -ne $PrJson.number) {
                $PrNumber = "$($PrJson.number)"
            }
        } catch {}
    }
}

if (-not $PrNumber) {
    Write-Host "No open PR found for this branch. Please push, open a PR, and run this script again." -ForegroundColor Yellow
    exit 0
}

if ([string]::IsNullOrWhiteSpace($SummaryPath) -or -not (Test-Path -LiteralPath $SummaryPath -PathType Leaf)) {
    Write-Host "Summary file not found at $SummaryPath" -ForegroundColor Yellow
    exit 0
}

if (-not $Version) {
    $Version = (Get-Item -LiteralPath $SummaryPath).Directory.Name
}

$Summary = $null
try {
    $Summary = Get-Content -LiteralPath $SummaryPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Host "Failed to read or parse summary JSON at ${SummaryPath}: $_" -ForegroundColor Yellow
    exit 0
}

$Flows = @($Summary | Where-Object { $null -ne $_ -and -not [string]::IsNullOrWhiteSpace($_.flow) })
if ($Flows.Count -eq 0) {
    Write-Host "Summary at $SummaryPath contained no flow results." -ForegroundColor Yellow
    exit 0
}

$CommentBody = "<!-- e2e-evidence -->`n### :test_tube: E2E Test Evidence (Darwin Trader)`n`n"
$CommentBody += "| Flow | Status |`n|---|---|`n"

$AnyFailed = $false
foreach ($flow in $Flows) {
    $check = [char]::ConvertFromUtf32(0x2705)
    $cross = [char]::ConvertFromUtf32(0x274C)
    $StatusIcon = if ($flow.passed) { $check } else { $cross }
    
    $StatusCell = $StatusIcon
    if (-not $flow.passed -and $flow.screenshot) {
        $ScreenshotUrl = "https://github.com/AntaresAndBharani/darwin-trader-qa/releases/download/$Version/$($flow.screenshot)"
        $camera = [char]::ConvertFromUtf32(0x1F4F8)
        $StatusCell += " [$($camera) Failure Screenshot]($ScreenshotUrl)"
    }

    $CommentBody += "| $($flow.flow) | $StatusCell |`n"
    if (-not $flow.passed) { $AnyFailed = $true }
}

if ($AnyFailed) {
    $cross = [char]::ConvertFromUtf32(0x274C)
    $CommentBody += "`n**Status:** $($cross) Some flows failed.`n"
} else {
    $check = [char]::ConvertFromUtf32(0x2705)
    $CommentBody += "`n**Status:** $($check) All flows passed.`n"
}

$link = [char]::ConvertFromUtf32(0x1F517)
$CommentBody += "`n[$($link) View Full HTML Report & Screenshots](https://github.com/AntaresAndBharani/darwin-trader-qa/releases/download/$Version/report.html)`n"

$tempBodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "e2e-evidence-body-$([guid]::NewGuid()).md"
try {
    [System.IO.File]::WriteAllText($tempBodyFile, $CommentBody, (New-Object System.Text.UTF8Encoding $false))

    $RestCommentsRaw = gh api "repos/AntaresAndBharani/darwin-trader/issues/$PrNumber/comments" --paginate 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to list comments on PR #$PrNumber."
        exit 0
    }

    $RestComments = @()
    if (-not [string]::IsNullOrWhiteSpace($RestCommentsRaw)) {
        try {
            $RestComments = @($RestCommentsRaw | ConvertFrom-Json)
        } catch {
            Write-Warning "Failed to parse comments JSON: $_"
            exit 0
        }
    }

    $CurrentUser = gh api user --jq .login 2>$null
    $RestComment = $RestComments | Where-Object { ($null -eq $CurrentUser -or $_.user.login -eq $CurrentUser) -and $_.body -match "^<!-- e2e-evidence -->" } | Select-Object -Last 1

    if ($RestComment) {
        Write-Host "Updating existing PR comment on PR #$PrNumber (ID: $($RestComment.id))..."
        gh api "repos/AntaresAndBharani/darwin-trader/issues/comments/$($RestComment.id)" -X PATCH --silent -F body=@$tempBodyFile
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to update comment on PR #$PrNumber."
            exit 0
        }
    } else {
        Write-Host "Posting new PR comment on PR #$PrNumber..."
        gh api "repos/AntaresAndBharani/darwin-trader/issues/$PrNumber/comments" -X POST --silent -F body=@$tempBodyFile
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to post comment on PR #$PrNumber."
            exit 0
        }
    }

    Write-Host "E2E Evidence posted successfully." -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $tempBodyFile -Force -ErrorAction SilentlyContinue
}
