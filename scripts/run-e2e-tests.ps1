<#
.SYNOPSIS
    Runs local end-to-end (E2E) UI test flows using Maestro on an Android emulator or physical device for Darwin Trader.

.DESCRIPTION
    1. Verifies/Starts the Android emulator (Pixel_10_API_35 by default).
    2. Builds/installs the latest snapshot APK onto the target device.
    3. Runs declarative Maestro test flows (e2e/flows/*.yaml).
    4. Generates an execution report and captures failure screenshots.

.EXAMPLE
    .\scripts\run-e2e-tests.ps1
    .\scripts\run-e2e-tests.ps1 -Delta
    .\scripts\run-e2e-tests.ps1 -Flow "e2e/flows/01_dashboard_flow.yaml"
    .\scripts\run-e2e-tests.ps1 -AvdName "Pixel_10_API_35" -SkipBuild
#>
param (
    [string]$Flow = "e2e/flows",
    [string]$AvdName = "Pixel_10_API_35",
    [switch]$SkipBuild,
    [switch]$Headless,
    [switch]$CaptureArtifacts,
    [string]$OutputRepo = "..\darwin-trader-qa",
    [string]$Version = "latest",
    [switch]$PushArtifacts,
    [switch]$Delta,
    [string[]]$Tags = @(),
    [string]$BaseBranch = "main"
)

$ErrorActionPreference = "Stop"

if ($Version -eq "latest") {
    $PrNumber = ""
    if ($null -ne (Get-Command gh -ErrorAction SilentlyContinue)) {
        try {
            $PrJson = gh pr view --json number 2>$null | ConvertFrom-Json
            if ($null -ne $PrJson -and $null -ne $PrJson.number) {
                $PrNumber = $PrJson.number
            }
        } catch {}
    }
    if ($PrNumber) {
        $Version = "e2e-pr-$PrNumber"
    } else {
        $Branch = git rev-parse --abbrev-ref HEAD 2>$null
        if (-not $Branch) { $Branch = "local" }
        $BranchSafe = $Branch -replace '[^a-zA-Z0-9-]', '-'
        $Version = "e2e-$BranchSafe"
    }
}
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " [APP] Darwin Trader - Local E2E Test Suite" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Locate ADB
$AdbPath = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
if (!(Test-Path $AdbPath)) {
    $AdbCmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($AdbCmd) { $AdbPath = $AdbCmd.Source } else {
        Write-Error "Could not find adb.exe in Android SDK. Please ensure Android SDK is installed."
    }
}

# 2. Locate Maestro
$MaestroPath = "$env:USERPROFILE\.maestro\bin\maestro.bat"
if (!(Test-Path $MaestroPath)) {
    $MaestroCmd = Get-Command maestro -ErrorAction SilentlyContinue
    if ($MaestroCmd) { $MaestroPath = $MaestroCmd.Source } else {
        Write-Error "Maestro CLI not found at '$MaestroPath'. Please install Maestro CLI."
    }
}

# 3. Check for running devices
Write-Host "`n[1/4] Checking connected Android devices..." -ForegroundColor Yellow
$Devices = & $AdbPath devices | Where-Object { $_ -match "\bdevice$" }
if (-not $Devices) {
    Write-Host "No active Android device found. Booting AVD '$AvdName'..." -ForegroundColor Yellow
    if (Get-Command android -ErrorAction SilentlyContinue) {
        android emulator start $AvdName
    } else {
        $EmuPath = "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe"
        if (Test-Path $EmuPath) {
            Start-Process -FilePath $EmuPath -ArgumentList "-avd", $AvdName, "-no-snapshot-load"
        }
    }
    Write-Host "Waiting for device to boot..." -ForegroundColor Yellow
    & $AdbPath wait-for-device
}

$OnlineDevice = (& $AdbPath devices | Where-Object { $_ -match "\bdevice$" } | Select-Object -First 1).Split("`t")[0]
Write-Host "Connected device: $OnlineDevice" -ForegroundColor Green

# 4. Build and Install APK
if (-not $SkipBuild) {
    Write-Host "`n[2/4] Building latest snapshot APK..." -ForegroundColor Yellow
    $OrigLocation = Get-Location
    try {
        Set-Location "android"
        if ($env:JAVA_HOME -and (Test-Path $env:JAVA_HOME)) {
            .\gradlew.bat assembleSnapshot -PsnapshotLabel=localtest --no-daemon
        } else {
            $env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
            .\gradlew.bat assembleSnapshot -PsnapshotLabel=localtest --no-daemon
        }
    } finally {
        Set-Location $OrigLocation
    }
    
    if (!(Test-Path "local_test")) { New-Item -ItemType Directory -Path "local_test" | Out-Null }
    if (Test-Path "android\app\build\outputs\apk\snapshot\release\app-snapshot-release.apk") {
        Copy-Item -Path "android\app\build\outputs\apk\snapshot\release\app-snapshot-release.apk" -Destination "local_test\latest.apk" -Force
    } elseif (Test-Path "android\app\build\outputs\apk\snapshot\debug\app-snapshot-debug.apk") {
        Copy-Item -Path "android\app\build\outputs\apk\snapshot\debug\app-snapshot-debug.apk" -Destination "local_test\latest.apk" -Force
    } elseif (Test-Path "android\app\build\outputs\apk\snapshot\app-snapshot.apk") {
        Copy-Item -Path "android\app\build\outputs\apk\snapshot\app-snapshot.apk" -Destination "local_test\latest.apk" -Force
    }
}

Write-Host "`n[3/4] Installing latest APK to $OnlineDevice..." -ForegroundColor Yellow
if (Test-Path "local_test\latest.apk") {
    & $AdbPath -s $OnlineDevice install -r "local_test\latest.apk"
} else {
    Write-Warning "local_test\latest.apk not found. Skipping install step."
}

# 5. Determine Active Tags / Delta Coverage
$ActiveTags = @()
if ($Tags.Count -gt 0) {
    $ActiveTags = $Tags
    Write-Host "`n[TAGS] Targeting explicit tag(s): $($ActiveTags -join ', ')" -ForegroundColor Cyan
} elseif ($Delta) {
    Write-Host "`n[DELTA] Computing targeted test coverage against '$BaseBranch'..." -ForegroundColor Cyan
    
    $ChangedFiles = @()
    try {
        $DiffTarget = "origin/$BaseBranch"
        $null = git rev-parse --verify $DiffTarget 2>&1
        if ($LASTEXITCODE -ne 0) { $DiffTarget = $BaseBranch }
        
        $BranchDiff = git diff --name-only "$DiffTarget...HEAD" 2>$null
        if ($BranchDiff) { $ChangedFiles += $BranchDiff }
        
        $WorkingDiff = git diff --name-only HEAD 2>$null
        if ($WorkingDiff) { $ChangedFiles += $WorkingDiff }
        
        $Untracked = git ls-files --others --exclude-standard 2>$null
        if ($Untracked) { $ChangedFiles += $Untracked }
    } catch {}
    
    $ChangedFiles = $ChangedFiles | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique
    
    if (-not $ChangedFiles -or $ChangedFiles.Count -eq 0) {
        Write-Host "[DELTA] No changed files detected against $BaseBranch. Running full suite as safety baseline." -ForegroundColor Yellow
        $ActiveTags = @()
    } else {
        Write-Host "[DELTA] Changed files detected ($($ChangedFiles.Count)):" -ForegroundColor DarkGray
        foreach ($file in $ChangedFiles) { Write-Host " - $file" -ForegroundColor DarkGray }
        
        $MappingFile = "e2e/flow-mapping.json"
        if (-not (Test-Path $MappingFile)) {
            Write-Warning "[DELTA] Mapping file '$MappingFile' not found. Falling back to full test suite."
            $ActiveTags = @()
        } else {
            $Mapping = Get-Content $MappingFile -Raw | ConvertFrom-Json
            $ResolvedTags = [System.Collections.Generic.HashSet[string]]::new()
            
            foreach ($rule in $Mapping.rules) {
                $RegexPattern = '^' + ([regex]::Escape($rule.pattern) -replace '\\\*\*\\?', '.*' -replace '\\\*', '[^/\\]*') + '$'
                $NormalizedPattern = $rule.pattern.Replace('\', '/')
                
                foreach ($file in $ChangedFiles) {
                    $NormalizedFile = $file.Replace('\', '/')
                    if ($NormalizedFile -match $RegexPattern -or $NormalizedFile -like $NormalizedPattern) {
                        foreach ($t in $rule.tags) { [void]$ResolvedTags.Add($t) }
                    }
                }
            }
            
            if ($ResolvedTags.Count -eq 0) {
                Write-Host "[DELTA] Changed files do not map to specific UI tags. Running full test suite as safety baseline." -ForegroundColor Yellow
                $ActiveTags = @()
            } else {
                $ActiveTags = [string[]]$ResolvedTags
                Write-Host "[DELTA] Resolved targeted tag(s): $($ActiveTags -join ', ')" -ForegroundColor Green
            }
        }
    }
}

# 6. Execute Maestro Flows
Write-Host "`n[4/4] Running Maestro flows ($Flow)..." -ForegroundColor Yellow

$FlowFiles = @()
if (Test-Path $Flow -PathType Container) {
    $FlowFiles = Get-ChildItem -Path $Flow -Filter "*.yaml" | Sort-Object Name
} elseif (Test-Path $Flow) {
    $FlowFiles = @(Get-Item $Flow)
}

if ($ActiveTags.Count -gt 0) {
    $FilteredFlowFiles = @()
    foreach ($f in $FlowFiles) {
        $Content = Get-Content -LiteralPath $f.FullName -Raw
        $FlowHasTag = $false
        foreach ($tag in $ActiveTags) {
            if ($Content -match "(?m)^\s*-\s*['`"]?$tag['`"]?\s*$") {
                $FlowHasTag = $true
                break
            }
        }
        if ($FlowHasTag) {
            $FilteredFlowFiles += $f
        }
    }
    $FlowFiles = $FilteredFlowFiles
}

Write-Host "Discovered $($FlowFiles.Count) active flow(s) to execute." -ForegroundColor Cyan

$ExecutionResults = @()
$OverallPassed = $true

foreach ($flowFile in $FlowFiles) {
    Write-Host "`nRunning flow: $($flowFile.Name)..." -ForegroundColor Cyan
    $MaestroArgs = @("test", $flowFile.FullName)
    
    $FlowPassed = $true
    try {
        & $MaestroPath @MaestroArgs
        if ($LASTEXITCODE -ne 0) { $FlowPassed = $false }
    } catch {
        $FlowPassed = $false
    }
    
    if (-not $FlowPassed) {
        $OverallPassed = $false
        Write-Host "Flow failed: $($flowFile.Name)" -ForegroundColor Red
        
        $ScreenshotName = "failure-$($flowFile.BaseName).png"
        if (!(Test-Path "docs\screenshots")) { New-Item -ItemType Directory -Path "docs\screenshots" | Out-Null }
        & $AdbPath -s $OnlineDevice exec-out screencap -p > "docs\screenshots\$ScreenshotName"
        
        $ExecutionResults += [PSCustomObject]@{
            flow = $flowFile.Name
            passed = $false
            screenshot = $ScreenshotName
        }
    } else {
        Write-Host "Flow passed: $($flowFile.Name)" -ForegroundColor Green
        $ExecutionResults += [PSCustomObject]@{
            flow = $flowFile.Name
            passed = $true
            screenshot = $null
        }
    }
}

if (!(Test-Path "local_test")) { New-Item -ItemType Directory -Path "local_test" | Out-Null }
$SummaryJson = $ExecutionResults | ConvertTo-Json
$SummaryJson | Set-Content "local_test\summary.json"

Write-Host "`n==========================================" -ForegroundColor Cyan
if ($OverallPassed) {
    Write-Host " [PASS] All E2E flows completed successfully!" -ForegroundColor Green
} else {
    Write-Host " [FAIL] Some E2E flows failed. See execution summary." -ForegroundColor Red
}
Write-Host "==========================================" -ForegroundColor Cyan
