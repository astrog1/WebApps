param(
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  .\start_local.ps1 start    # Start all local services"
    Write-Host "  .\start_local.ps1 stop     # Stop all local services"
    Write-Host "  .\start_local.ps1 status   # Show service status"
    Write-Host "  .\start_local.ps1 restart  # Restart all local services"
    Write-Host ""
    Write-Host "Optional environment variables:"
    Write-Host "  BLACKJACK_PORT (default: 5101)"
    Write-Host "  YAHTZEE_PORT   (default: 5102)"
    Write-Host "  MATH_PORT      (default: 5103)"
    Write-Host "  HUB_PORT       (default: 8080)"
    Write-Host "  HOST_BIND      (default: 0.0.0.0)"
    Write-Host "  OPENAI_API_KEY (optional for Daily Math /generate)"
}

if ([string]::IsNullOrWhiteSpace($Action)) {
    $Action = "start"
}

$actionNormalized = $Action.ToLowerInvariant()
$validActions = @("start", "stop", "status", "restart", "help", "-h", "--help")
if ($validActions -notcontains $actionNormalized) {
    Show-Usage
    exit 1
}

$RootDir = Split-Path -Parent $PSCommandPath
$RuntimeDir = Join-Path $RootDir ".local_runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$PidDir = Join-Path $RuntimeDir "pids"

New-Item -ItemType Directory -Force -Path $RuntimeDir, $LogDir, $PidDir | Out-Null

function Get-EnvOrDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$DefaultValue
    )
    $item = Get-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
    if ($null -eq $item -or [string]::IsNullOrWhiteSpace($item.Value)) {
        return $DefaultValue
    }
    return $item.Value
}

$BLACKJACK_PORT = Get-EnvOrDefault -Name "BLACKJACK_PORT" -DefaultValue "5101"
$YAHTZEE_PORT = Get-EnvOrDefault -Name "YAHTZEE_PORT" -DefaultValue "5102"
$MATH_PORT = Get-EnvOrDefault -Name "MATH_PORT" -DefaultValue "5103"
$HUB_PORT = Get-EnvOrDefault -Name "HUB_PORT" -DefaultValue "8080"
$HOST_BIND = Get-EnvOrDefault -Name "HOST_BIND" -DefaultValue "0.0.0.0"

function Require-File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Hint
    )
    if (-not (Test-Path -Path $Path -PathType Leaf)) {
        Write-Host "Missing: $Path"
        Write-Host "Hint: $Hint"
        exit 1
    }
}

function Get-PidFile {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )
    return (Join-Path $PidDir "$Name.pid")
}

function Read-ProcessId {
    param(
        [Parameter(Mandatory = $true)][string]$PidFile
    )
    if (-not (Test-Path -Path $PidFile -PathType Leaf)) {
        return $null
    }

    $raw = (Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($null -eq $raw) {
        return $null
    }

    $trimmed = $raw.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        return $null
    }

    $parsed = 0
    if ([int]::TryParse($trimmed, [ref]$parsed)) {
        return $parsed
    }

    return $null
}

function Test-IsRunning {
    param(
        [Parameter(Mandatory = $false)][Nullable[int]]$ProcessId
    )
    if ($null -eq $ProcessId) {
        return $false
    }
    try {
        Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Set-TempEnvironment {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Values
    )

    $snapshot = @{}
    foreach ($key in $Values.Keys) {
        $item = Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue
        $snapshot[$key] = if ($null -eq $item) { $null } else { $item.Value }

        $newValue = [string]$Values[$key]
        if ([string]::IsNullOrWhiteSpace($newValue)) {
            Remove-Item -Path "Env:$key" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item -Path "Env:$key" -Value $newValue
        }
    }

    return $snapshot
}

function Restore-Environment {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Snapshot
    )
    foreach ($key in $Snapshot.Keys) {
        $value = $Snapshot[$key]
        if ($null -eq $value) {
            Remove-Item -Path "Env:$key" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}

function Start-One {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $false)][hashtable]$Environment = @{}
    )

    $pidFile = Get-PidFile -Name $Name
    $outLog = Join-Path $LogDir "$Name.out.log"
    $errLog = Join-Path $LogDir "$Name.err.log"

    $existingPid = Read-ProcessId -PidFile $pidFile
    if (Test-IsRunning -ProcessId $existingPid) {
        Write-Host "[$Name] already running (PID $existingPid)."
        return
    }

    Remove-Item -Path $pidFile -ErrorAction SilentlyContinue

    $snapshot = @{}
    if ($Environment.Count -gt 0) {
        $snapshot = Set-TempEnvironment -Values $Environment
    }

    try {
        $proc = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $Arguments `
            -WorkingDirectory $WorkingDirectory `
            -RedirectStandardOutput $outLog `
            -RedirectStandardError $errLog `
            -WindowStyle Hidden `
            -PassThru
    }
    finally {
        if ($Environment.Count -gt 0) {
            Restore-Environment -Snapshot $snapshot
        }
    }

    Start-Sleep -Milliseconds 300
    if (Test-IsRunning -ProcessId $proc.Id) {
        Set-Content -Path $pidFile -Value $proc.Id
        Write-Host "[$Name] started (PID $($proc.Id))"
        Write-Host "[$Name] logs: $outLog ; $errLog"
    }
    else {
        Write-Host "[$Name] failed to start. Check logs in $LogDir"
    }
}

function Stop-One {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )

    $pidFile = Get-PidFile -Name $Name
    $processId = Read-ProcessId -PidFile $pidFile

    if (-not (Test-IsRunning -ProcessId $processId)) {
        Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
        Write-Host "[$Name] not running."
        return
    }

    try {
        Stop-Process -Id $processId -ErrorAction Stop
        Start-Sleep -Milliseconds 400
        if (Test-IsRunning -ProcessId $processId) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[$Name] stopped."
    }
    catch {
        Write-Host "[$Name] stop failed for PID $processId. Try manually: Stop-Process -Id $processId -Force"
    }
    finally {
        Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
    }
}

function Status-One {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )

    $pidFile = Get-PidFile -Name $Name
    $processId = Read-ProcessId -PidFile $pidFile
    if (Test-IsRunning -ProcessId $processId) {
        Write-Host "[$Name] running (PID $processId)"
    }
    else {
        Write-Host "[$Name] stopped"
    }
}

function Get-LanIp {
    $addresses = [System.Net.Dns]::GetHostEntry([System.Net.Dns]::GetHostName()).AddressList
    $ipv4 = $addresses |
        Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and -not $_.IPAddressToString.StartsWith("127.") } |
        Select-Object -First 1

    if ($null -eq $ipv4) {
        return "YOUR_WINDOWS_PC_IP"
    }

    return $ipv4.IPAddressToString
}

function Print-Urls {
    $lanIp = Get-LanIp
    Write-Host ""
    Write-Host "Open locally:"
    Write-Host "  Hub:       http://localhost:$HUB_PORT"
    Write-Host "  Blackjack: http://localhost:$BLACKJACK_PORT"
    Write-Host "  Yahtzee:   http://localhost:$YAHTZEE_PORT"
    Write-Host "  DailyMath: http://localhost:$MATH_PORT"
    Write-Host ""
    Write-Host "Open from another PC on your LAN:"
    Write-Host "  Hub:       http://${lanIp}:$HUB_PORT"
}

function Start-All {
    $blackjackPython = Join-Path $RootDir "blackjack-game\.venv\Scripts\python.exe"
    $yahtzeePython = Join-Path $RootDir "yahtzee-game\.venv\Scripts\python.exe"
    $mathPython = Join-Path $RootDir "Daily_math_games_v2\.venv\Scripts\python.exe"
    $homePageIndex = Join-Path $RootDir "home-page\index.html"

    Require-File -Path $blackjackPython -Hint "Create blackjack-game\.venv and install requirements."
    Require-File -Path $yahtzeePython -Hint "Create yahtzee-game\.venv and install requirements."
    Require-File -Path $mathPython -Hint "Create Daily_math_games_v2\.venv and install requirements."
    Require-File -Path $homePageIndex -Hint "Expected file at home-page\index.html."

    if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        Write-Host "[daily-math] OPENAI_API_KEY is not set. /generate will fail until you set it."
    }

    Start-One `
        -Name "blackjack" `
        -WorkingDirectory (Join-Path $RootDir "blackjack-game") `
        -FilePath $blackjackPython `
        -Arguments @("app.py") `
        -Environment @{ PORT = $BLACKJACK_PORT }

    Start-One `
        -Name "yahtzee" `
        -WorkingDirectory (Join-Path $RootDir "yahtzee-game") `
        -FilePath $yahtzeePython `
        -Arguments @("app.py") `
        -Environment @{ PORT = $YAHTZEE_PORT }

    $dailyMathEnv = @{}
    if (-not [string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        $dailyMathEnv["OPENAI_API_KEY"] = $env:OPENAI_API_KEY
    }

    Start-One `
        -Name "daily-math" `
        -WorkingDirectory (Join-Path $RootDir "Daily_math_games_v2") `
        -FilePath $mathPython `
        -Arguments @("-m", "uvicorn", "app.main:app", "--host", $HOST_BIND, "--port", $MATH_PORT) `
        -Environment $dailyMathEnv

    Start-One `
        -Name "home-page" `
        -WorkingDirectory $RootDir `
        -FilePath $mathPython `
        -Arguments @("-m", "http.server", $HUB_PORT, "--bind", $HOST_BIND, "--directory", "home-page")

    Print-Urls
    Write-Host ""
    Write-Host "Logs: $LogDir"
    Write-Host "Stop all: .\start_local.ps1 stop"
}

function Stop-All {
    Stop-One -Name "home-page"
    Stop-One -Name "daily-math"
    Stop-One -Name "yahtzee"
    Stop-One -Name "blackjack"
}

function Status-All {
    Status-One -Name "blackjack"
    Status-One -Name "yahtzee"
    Status-One -Name "daily-math"
    Status-One -Name "home-page"
}

switch ($actionNormalized) {
    "start" {
        Start-All
    }
    "stop" {
        Stop-All
    }
    "status" {
        Status-All
    }
    "restart" {
        Stop-All
        Start-All
    }
    "help" {
        Show-Usage
    }
    "-h" {
        Show-Usage
    }
    "--help" {
        Show-Usage
    }
}
