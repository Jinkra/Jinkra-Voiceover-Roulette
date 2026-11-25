param(
    [Parameter(Mandatory)][string]$DriverBinary,
    [Parameter(Mandatory)][string]$Symbols,
    [Parameter(Mandatory)][string]$InfVerif,
    [Parameter(Mandatory)][string]$Inf2Cat,
    [Parameter(Mandatory)][string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$driverPath = (Resolve-Path -LiteralPath $DriverBinary).ProviderPath
$symbolsPath = (Resolve-Path -LiteralPath $Symbols).ProviderPath
$verifyTool = (Resolve-Path -LiteralPath $InfVerif).ProviderPath
$catalogTool = (Resolve-Path -LiteralPath $Inf2Cat).ProviderPath
if ([IO.Path]::GetFileName($driverPath) -ne "JinkraVad.sys" -or
    [IO.Path]::GetFileName($symbolsPath) -ne "JinkraVad.pdb") {
    throw "Expected JinkraVad.sys and its matching JinkraVad.pdb."
}

$output = (New-Item -Path $OutputDirectory -ItemType Directory -Force).FullName
$work = New-Item -Path ([IO.Path]::GetTempPath()) -Name ("jinkra-signing-" + [guid]::NewGuid()) -ItemType Directory
$cabinet = "Jinkra-Virtual-Mic-v0.3.0-x64-signing.cab"
$files = @("JinkraVad.inf", "JinkraVad.sys", "JinkraVad.cat", "JinkraVad.pdb")
$inf = Join-Path $work.FullName $files[0]
try {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "package/JinkraVad.inf") -Destination $inf
    Copy-Item -LiteralPath $driverPath -Destination (Join-Path $work.FullName $files[1])
    & $verifyTool /w $inf
    if ($LASTEXITCODE -ne 0) { throw "InfVerif failed with exit code $LASTEXITCODE." }

    & $catalogTool "/driver:$($work.FullName)" /os:10_VB_X64,10_CO_X64,10_NI_X64,10_GE_X64
    if ($LASTEXITCODE -ne 0) { throw "Inf2Cat failed with exit code $LASTEXITCODE." }
    Copy-Item -LiteralPath $symbolsPath -Destination (Join-Path $work.FullName $files[3])

    Push-Location -LiteralPath $work.FullName
    try {
        @(
            ".OPTION EXPLICIT"
            ".Set MaxDiskSize=0"
            ".Set CabinetNameTemplate=$cabinet"
            ".Set DiskDirectoryTemplate=."
            ".Set CompressionType=MSZIP"
            ".Set Cabinet=on"
            ".Set Compress=on"
            ".Set DestinationDir=JinkraVad"
        ) + $files | Set-Content -LiteralPath "package.ddf" -Encoding ascii
        & makecab.exe /F package.ddf
        if ($LASTEXITCODE -ne 0) { throw "MakeCab failed with exit code $LASTEXITCODE." }
        $destination = Join-Path $output $cabinet
        Copy-Item -LiteralPath $cabinet -Destination $destination -Force
        Get-FileHash -LiteralPath $destination -Algorithm SHA256
        Write-Host "Unsigned submission CAB. Complete Microsoft signing before installing."
    }
    finally {
        Pop-Location
    }
}
finally {
    foreach ($name in ($files + @($cabinet, "package.ddf", "setup.inf", "setup.rpt"))) {
        $path = Join-Path $work.FullName $name
        if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path }
    }
    if (-not (Get-ChildItem -LiteralPath $work.FullName -Force)) {
        [IO.Directory]::Delete($work.FullName, $false)
    }
}
