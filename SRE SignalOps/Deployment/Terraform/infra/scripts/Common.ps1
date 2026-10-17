Set-StrictMode -Version Latest

function Invoke-LabNative {
    param([string]$Command, [string[]]$Arguments)
    $result = & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE."
    }
    $result
}

function Get-LabSources {
    $packaged = Join-Path $PSScriptRoot '..\apps'
    if (Test-Path -LiteralPath $packaged -PathType Container) {
        return (Resolve-Path -LiteralPath $packaged).Path
    }
    $checkout = Join-Path $PSScriptRoot '..\..\..\..\..\Student\Resources'
    if (Test-Path -LiteralPath $checkout -PathType Container) {
        return (Resolve-Path -LiteralPath $checkout).Path
    }
    throw 'Application sources are missing. Extract the complete SignalOps Terraform download.'
}

function Get-LabImages {
    $sources = Get-LabSources
    $definitions = @(
        @('grubify_api', 'grubify-api', 'grubify\GrubifyApi', 'Dockerfile'),
        @('grubify_frontend', 'grubify-frontend', 'grubify\grubify-frontend', 'Dockerfile'),
        @('lisbon', 'lisbon-parking-api', 'parking-manager\backend', 'lisbon-parking-api\Dockerfile'),
        @('berlin', 'berlin-parking-api', 'parking-manager\backend', 'berlin-parking-api\Dockerfile'),
        @('berlin_mcp', 'berlin-mcp-server', 'parking-manager\backend\berlin-mcp-server', 'Dockerfile'),
        @('chaos_control', 'chaos-control', 'parking-manager\backend\chaos-control', 'Dockerfile'),
        @('vm_health', 'vm-health-control', 'parking-manager\backend\vm-health-control', 'Dockerfile')
    )
    foreach ($definition in $definitions) {
        $context = Join-Path $sources $definition[2]
        $dockerfile = Join-Path $context $definition[3]
        if (-not (Test-Path -LiteralPath $dockerfile -PathType Leaf)) {
            throw "Missing build dependency: $dockerfile"
        }
        [pscustomobject]@{
            Key = $definition[0]
            Repository = "signalops/$($definition[1])"
            Context = $context
            Dockerfile = $dockerfile
        }
    }
}

function New-LabVmPayload {
    param([ValidateSet('madrid', 'paris')][string]$City)
    $backend = Join-Path (Get-LabSources) 'parking-manager\backend'
    $files = foreach ($directory in @("$City-parking-api", 'shared')) {
        Get-ChildItem -LiteralPath (Join-Path $backend $directory) -File |
            Where-Object { $_.Extension -eq '.js' -or $_.Name -in @('package.json', 'package-lock.json') } |
            ForEach-Object {
                @{
                    path = "$directory/$($_.Name)"
                    content = [Convert]::ToBase64String([IO.File]::ReadAllBytes($_.FullName))
                }

            }
    }
    foreach ($required in @("$City-parking-api/server.js", "$City-parking-api/package-lock.json", 'shared/chaosMiddleware.js')) {
        if ($required -notin $files.path) { throw "Missing VM application dependency: $required" }
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject @($files) -Depth 5 -Compress))
    $buffer = [IO.MemoryStream]::new()
    $gzip = [IO.Compression.GZipStream]::new($buffer, [IO.Compression.CompressionLevel]::Optimal, $true)
    try {
        $gzip.Write($bytes, 0, $bytes.Length)
    } finally {
        $gzip.Dispose()
    }
    try { [Convert]::ToBase64String($buffer.ToArray()) } finally { $buffer.Dispose() }
}

function Copy-LabBuildContext {
    param([string]$Source, [string]$Destination)
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($entry in Get-ChildItem -LiteralPath $Source -Force) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Build source links are not allowed: $($entry.FullName)" }
        if ($entry.PSIsContainer) {
            if ($entry.Name -notin @('node_modules', 'bin', 'obj', 'build', 'dist', 'coverage', '.git', '.azure', '.terraform', 'logs')) {
                Copy-LabBuildContext -Source $entry.FullName -Destination (Join-Path $Destination $entry.Name)
            }
        } elseif ($entry.Name -match '\.(cs|csproj|js|jsx|cjs|mjs|ts|tsx|css|html|conf|sh|svg|png|jpe?g|gif|ico|webp|woff2?|ttf|txt)$' -or
            $entry.Name -match '^(Dockerfile|\.dockerignore|package(-lock)?\.json|appsettings\.json|tsconfig\.json|manifest\.json)$') {
            Copy-Item -LiteralPath $entry.FullName -Destination $Destination
        }
    }
}
