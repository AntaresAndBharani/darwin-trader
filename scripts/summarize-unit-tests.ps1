param (
    [string]$ResultsDir = "android/app/build/test-results",
    [string]$OutFile = "unit-test-summary.md",
    [string]$PrNumber = "",
    [string]$Repo = $(if ($env:GITHUB_REPOSITORY) { $env:GITHUB_REPOSITORY } else { "AntaresAndBharani/darwin-trader" }),
    [string]$ArtifactName = ""
)

if ([string]::IsNullOrWhiteSpace($Repo)) {
    $Repo = if ($env:GITHUB_REPOSITORY) { $env:GITHUB_REPOSITORY } else { "AntaresAndBharani/darwin-trader" }
}

$EvidenceMarker = "<!-- unit-test-evidence -->"

function ConvertTo-RelativePath ([string]$text) {
    if (-not $text) { return "" }
    
    if ($env:GITHUB_WORKSPACE) {
        $text = $text.Replace($env:GITHUB_WORKSPACE + "/", "").Replace($env:GITHUB_WORKSPACE + "\", "").Replace($env:GITHUB_WORKSPACE, "")
    }
    
    $text = [regex]::Replace($text, '(?i)/home/runner/work/[^/\r\n]+/[^/\r\n]+/', '')
    $text = [regex]::Replace($text, '(?i)[a-zA-Z]:[\\/]a[\\/][^\\/\r\n]+[\\/][^\\/\r\n]+[\\/]', '')
    $text = [regex]::Replace($text, '(?i)[a-zA-Z]:[\\/](?:[^\\/\r\n]+[\\/])+darwin-trader[\\/]', '')
    
    return $text
}

function Limit-TextLines ([string]$text, [int]$maxLines = 40) {
    if (-not $text) { return "" }
    
    $lines = $text -split '\r?\n'
    if ($lines.Count -gt $maxLines) {
        $truncatedLines = $lines[0..($maxLines - 1)]
        return ($truncatedLines -join "`n") + "`n... (truncated)"
    }
    return $lines -join "`n"
}

function Format-StackTrace ([string]$trace) {
    if (-not $trace) { return "" }
    
    $trace = ConvertTo-RelativePath -text $trace
    $trace = Limit-TextLines -text $trace -maxLines 40
    
    return $trace.Trim()
}

function Format-FailureMessage ([string]$message) {
    if (-not $message) { return "" }
    
    $message = ConvertTo-RelativePath -text $message
    $message = Limit-TextLines -text $message -maxLines 40
    
    $backtickMatches = [regex]::Matches($message, '`+')
    $maxRun = 0
    if ($backtickMatches.Count -gt 0) {
        $maxRun = ($backtickMatches | Measure-Object -Property Length -Maximum).Maximum
    }
    
    if ($message -match '\r?\n') {
        $fenceLen = [Math]::Max(3, $maxRun + 1)
        $fence = '`' * $fenceLen
        return "**Message:**`n$fence`n$message`n$fence`n`n"
    } else {
        $delimLen = [Math]::Max(1, $maxRun + 1)
        $delim = '`' * $delimLen
        if ($message.StartsWith('`') -or $message.EndsWith('`')) {
            $content = " $message "
        } else {
            $content = $message
        }
        return "**Message:** $delim$content$delim`n`n"
    }
}

function Write-SummaryOutput ([string]$content) {
    if (-not [string]::IsNullOrWhiteSpace($OutFile)) {
        try {
            $outDir = [System.IO.Path]::GetDirectoryName($OutFile)
            if (-not [string]::IsNullOrWhiteSpace($outDir) -and -not (Test-Path -Path $outDir)) {
                [System.IO.Directory]::CreateDirectory($outDir) | Out-Null
            }
            [System.IO.File]::WriteAllText($OutFile, $content, (New-Object System.Text.UTF8Encoding $false))
        } catch {
            Write-Warning "Failed to write summary to '$OutFile': $_"
        }
    }
}

function Publish-StickyPrComment ([string]$content, [string]$targetPr) {
    if (-not $targetPr) {
        return
    }

    if (-not [regex]::IsMatch($targetPr, '^\d+$')) {
        Write-Warning "Invalid PR number '$targetPr'. Must be numeric."
        return
    }

    $tempBodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "unit-test-evidence-$([guid]::NewGuid()).md"
    try {
        [System.IO.File]::WriteAllText($tempBodyFile, $content, (New-Object System.Text.UTF8Encoding $false))

        $commentsJson = gh api "repos/$Repo/issues/$targetPr/comments" --paginate 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to query comments for PR #$targetPr."
            return
        }

        $existingComment = $null
        if ($commentsJson) {
            $comments = $commentsJson | ConvertFrom-Json
            $existingComment = $comments | Where-Object { $_.body -match $EvidenceMarker } | Select-Object -Last 1
        }

        if ($existingComment) {
            Write-Host "Updating existing unit test summary comment (ID: $($existingComment.id)) on PR #$targetPr..."
            gh api "repos/$Repo/issues/comments/$($existingComment.id)" -X PATCH -F body=@$tempBodyFile --silent
        } else {
            Write-Host "Posting new unit test summary comment to PR #$targetPr..."
            gh api "repos/$Repo/issues/$targetPr/comments" -X POST -F body=@$tempBodyFile --silent
        }
    } catch {
        Write-Warning "Failed to publish PR comment: $_"
    } finally {
        if (Test-Path -LiteralPath $tempBodyFile) {
            Remove-Item -LiteralPath $tempBodyFile -Force -ErrorAction SilentlyContinue
        }
    }
}

$xmlFiles = @()
if (Test-Path -Path $ResultsDir) {
    $xmlFiles = Get-ChildItem -Path $ResultsDir -Filter "*.xml" -Recurse | Sort-Object FullName
}

if ($xmlFiles.Count -eq 0) {
    $summary = "$EvidenceMarker`n### :warning: Unit Test Summary`n`nNo test result XML files found in `$ResultsDir` ($ResultsDir)."
    Write-SummaryOutput -content $summary
    Publish-StickyPrComment -content $summary -targetPr $PrNumber
    Write-Host $summary
    exit 0
}

$totalTests = 0
$totalFailures = 0
$totalErrors = 0
$totalSkipped = 0
$totalTime = 0.0
$failedSuites = @()

foreach ($file in $xmlFiles) {
    try {
        [xml]$xml = Get-Content -LiteralPath $file.FullName -Raw
        $suiteName = if ($xml.testsuite.name) { $xml.testsuite.name } else { $file.BaseName }
        $tests = if ($xml.testsuite.tests) { [int]$xml.testsuite.tests } else { 0 }
        $failures = if ($xml.testsuite.failures) { [int]$xml.testsuite.failures } else { 0 }
        $errors = if ($xml.testsuite.errors) { [int]$xml.testsuite.errors } else { 0 }
        $skipped = if ($xml.testsuite.skipped) { [int]$xml.testsuite.skipped } else { 0 }
        $time = if ($xml.testsuite.time) { [double]$xml.testsuite.time } else { 0.0 }

        $totalTests += $tests
        $totalFailures += $failures
        $totalErrors += $errors
        $totalSkipped += $skipped
        $totalTime += $time

        if ($failures -gt 0 -or $errors -gt 0) {
            $cases = @()
            foreach ($testcase in $xml.testsuite.testcase) {
                if ($testcase.failure -or $testcase.error) {
                    $failureNode = if ($testcase.failure) { $testcase.failure } else { $testcase.error }
                    $msg = if ($failureNode.message) { $failureNode.message } else { "" }
                    $trace = if ($failureNode.InnerText) { $failureNode.InnerText } else { "" }
                    $cases += [PSCustomObject]@{
                        Name = $testcase.name
                        Message = $msg
                        Trace = $trace
                    }
                }
            }
            $failedSuites += [PSCustomObject]@{
                Suite = $suiteName
                Cases = $cases
            }
        }
    } catch {
        Write-Warning "Could not parse '$($file.FullName)': $_"
    }
}

$totalPassed = $totalTests - ($totalFailures + $totalErrors + $totalSkipped)
if ($totalPassed -lt 0) { $totalPassed = 0 }

$check = [char]::ConvertFromUtf32(0x2705)
$cross = [char]::ConvertFromUtf32(0x274C)
$statusIcon = if ($totalFailures -eq 0 -and $totalErrors -eq 0) { $check } else { $cross }
$statusText = if ($totalFailures -eq 0 -and $totalErrors -eq 0) { "All unit tests passed" } else { "$($totalFailures + $totalErrors) failure(s) detected" }

$summary = "$EvidenceMarker`n### :microscope: Unit Test Execution Summary`n`n"
$summary += "**Status:** $statusIcon $statusText`n`n"
$summary += "| Metric | Count |`n|---|---|`n"
$summary += "| Total Tests | $totalTests |`n"
$summary += "| Passed | $totalPassed |`n"
$summary += "| Failed | $($totalFailures + $totalErrors) |`n"
$summary += "| Skipped | $totalSkipped |`n"
$summary += "| Execution Time | $([Math]::Round($totalTime, 2))s |`n`n"

if ($failedSuites.Count -gt 0) {
    $summary += "#### :x: Failures by Suite`n`n"
    foreach ($fs in $failedSuites) {
        $summary += "<details><summary><b>$($fs.Suite)</b> ($($fs.Cases.Count) failure(s))</summary>`n`n"
        foreach ($c in $fs.Cases) {
            $summary += "##### :small_red_triangle: $($c.Name)`n`n"
            if ($c.Message) {
                $summary += Format-FailureMessage -message $c.Message
            }
            if ($c.Trace) {
                $formattedTrace = Format-StackTrace -trace $c.Trace
                $fence = Get-BacktickFence -text $formattedTrace
                $summary += "<details><summary>Stack Trace</summary>`n`n$fence`n$formattedTrace`n$fence`n`n</details>`n`n"
            }
        }
        $summary += "</details>`n`n"
    }
}

Write-SummaryOutput -content $summary
Publish-StickyPrComment -content $summary -targetPr $PrNumber
Write-Host $summary
