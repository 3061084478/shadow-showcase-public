param(
  [string]$OutputDir = ".\build\cloudbase-mapping-build-admin"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ResolvedRepoRoot = (Resolve-Path $RepoRoot).Path
$ResolvedOutputDir = [System.IO.Path]::GetFullPath((Join-Path $ResolvedRepoRoot $OutputDir))

if (-not $ResolvedOutputDir.StartsWith($ResolvedRepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Output directory must stay inside the repository. Current output: $ResolvedOutputDir"
}

$FunctionSource = Join-Path $ResolvedRepoRoot "cloudbase-functions\mapping-build-admin"
$FunctionTarget = $ResolvedOutputDir

if (Test-Path -LiteralPath $FunctionTarget) {
  Remove-Item -LiteralPath $FunctionTarget -Recurse -Force
}

New-Item -ItemType Directory -Path $FunctionTarget | Out-Null

$FilesToCopy = @(
  "index.py",
  "requirements.txt",
  "README.md"
)

foreach ($RelativeFile in $FilesToCopy) {
  $SourceFile = Join-Path $FunctionSource $RelativeFile
  if (Test-Path -LiteralPath $SourceFile) {
    Copy-Item -LiteralPath $SourceFile -Destination (Join-Path $FunctionTarget $RelativeFile) -Force
  }
}

$SummaryPath = Join-Path $FunctionTarget "BUNDLE-CONTENTS.txt"
@(
  "CloudBase mapping delta bundle",
  "GeneratedAt=$([DateTime]::UtcNow.ToString('u'))",
  "RepoRoot=$ResolvedRepoRoot",
  "OutputDir=$ResolvedOutputDir",
  "",
  "Included:",
  "- index.py",
  "- requirements.txt",
  "- README.md"
) | Set-Content -LiteralPath $SummaryPath -Encoding UTF8

Write-Host "CloudBase mapping bundle generated: $ResolvedOutputDir"
Write-Host "Upload this whole directory to the CloudBase mapping-build-admin function."
