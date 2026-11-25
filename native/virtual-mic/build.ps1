param([ValidateSet("Debug", "Release")][string]$Configuration = "Release")

$ErrorActionPreference = "Stop"
$msbuild = Get-Command msbuild.exe -ErrorAction SilentlyContinue
if (-not $msbuild) {
    throw "Run from a Visual Studio 2022 Developer PowerShell with the C++ and WDK toolsets installed."
}

$projects = @(
    "driver/JinkraVad.vcxproj",
    "integration/driver-helper/jinkra-driver-helper.vcxproj"
)
foreach ($project in $projects) {
    & $msbuild.Source (Join-Path $PSScriptRoot $project) /restore /m "/p:Configuration=$Configuration" /p:Platform=x64 /p:SignMode=Off
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
Write-Host "Built the development binaries. Submit the driver package for Microsoft signing before retail deployment."
