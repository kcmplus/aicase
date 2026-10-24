$ErrorActionPreference = 'Stop'
$taskNode = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $taskNode) {
    $taskNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
}
if (-not (Test-Path -LiteralPath $taskNode)) { throw 'Node.js was not found. Please install Node.js 20 or newer.' }
$taskUrl = 'http://127.0.0.1:4173'
$taskReady = $false
try { $taskReady = (Invoke-WebRequest $taskUrl -TimeoutSec 2).Content -match 'AI CASE STUDIO|POPOMO' } catch {}
if (-not $taskReady) {
    $taskServer = Join-Path $PSScriptRoot 'server.mjs'
    Start-Process -FilePath $taskNode -ArgumentList ('"' + $taskServer + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    for ($taskAttempt = 0; $taskAttempt -lt 15; $taskAttempt++) {
        Start-Sleep -Milliseconds 200
        try { $taskReady = (Invoke-WebRequest $taskUrl -TimeoutSec 2).Content -match 'AI CASE STUDIO|POPOMO' } catch {}
        if ($taskReady) { break }
    }
}
if (-not $taskReady) { throw 'Preview could not start. Check whether port 4173 is occupied.' }
Start-Process $taskUrl
Write-Output "Preview is ready at $taskUrl"
