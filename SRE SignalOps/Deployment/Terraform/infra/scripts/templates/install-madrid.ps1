$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = 'C:\SignalOps'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$archive = Join-Path $root 'node.zip'
Invoke-WebRequest -UseBasicParsing -Uri 'https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip' -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71') {
    throw 'Node.js archive checksum mismatch.'
}
$task = Get-ScheduledTask -TaskName 'SignalOps-Madrid' -ErrorAction SilentlyContinue
if ($task) { Stop-ScheduledTask -InputObject $task }
Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
Remove-Item -LiteralPath $archive
$nodeDirectory = Join-Path $root 'node-v22.23.3-win-x64'
$env:PATH = "$nodeDirectory;$env:PATH"
$buffer = [IO.MemoryStream]::new([Convert]::FromBase64String('__PAYLOAD__'))
$gzip = [IO.Compression.GZipStream]::new($buffer, [IO.Compression.CompressionMode]::Decompress)
$reader = [IO.StreamReader]::new($gzip)
try { $files = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose(); $buffer.Dispose() }
foreach ($file in $files) {
    $target = [IO.Path]::GetFullPath((Join-Path $root $file.path))
    if (-not $target.StartsWith("$root\", [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid application payload path.' }
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    [IO.File]::WriteAllBytes($target, [Convert]::FromBase64String($file.content))
}
$app = Join-Path $root 'madrid-parking-api'
Push-Location $app
try {
    & (Join-Path $nodeDirectory 'npm.cmd') ci --omit=dev --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed: $LASTEXITCODE" }
} finally { Pop-Location }
@'
PORT=3002
NODE_ENV=production
EVENT_LOG_BACKEND=eventcreate
CHAOS_CONTROL_URL=__CHAOS_URL__
'@ | Set-Content -LiteralPath (Join-Path $app '.env') -Encoding ascii
if (-not [Diagnostics.EventLog]::SourceExists('MadridParkingAPI')) {
    New-EventLog -LogName Application -Source MadridParkingAPI
}
if (-not (Get-NetFirewallRule -Name 'SignalOps-Madrid-API' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'SignalOps-Madrid-API' -DisplayName 'SignalOps Madrid API (lab VNets)' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3002 -RemoteAddress '10.0.0.0/8' | Out-Null
}
$action = New-ScheduledTaskAction -Execute (Join-Path $nodeDirectory 'node.exe') -Argument 'server.js' -WorkingDirectory $app
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'SignalOps-Madrid' -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'SignalOps-Madrid'
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3002/health' -TimeoutSec 5
        if ($health.StatusCode -eq 200) {
            Write-EventLog -LogName Application -Source MadridParkingAPI -EventId 1000 -EntryType Information `
                -Message 'SignalOps Madrid application installation verified'
            Write-Output SIGNALOPS_VM_READY
            return
        }
    } catch [System.Net.WebException] {
        Write-Output "Waiting for Madrid health check ($attempt/30): $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 2
}
throw 'Madrid application health check failed.'
