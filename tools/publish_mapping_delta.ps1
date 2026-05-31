param(
  [Parameter(Mandatory = $true)]
  [string]$BaseUrl,

  [Parameter(Mandatory = $true)]
  [string]$AdminToken,

  [Parameter(Mandatory = $true)]
  [string[]]$LabeledInputs,

  [Parameter(Mandatory = $true)]
  [int]$BaseVersion,

  [string]$ReleaseDir = ".\build\mapping-release",

  [string]$MarkExportedStatus = "pending"
)

$ErrorActionPreference = "Stop"

function Get-NormalizedBaseUrl {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url
  )

  $Trimmed = $Url.Trim().TrimEnd("/")
  $KnownSuffixes = @(
    "/api/admin/mapping/upload-labeled",
    "/api/admin/mapping/latest-labeled",
    "/api/admin/mapping/publish-delta",
    "/api/admin/unknown-song/export",
    "/api/admin/unknown-song/stats",
    "/api/admin/unknown-song/mark-exported",
    "/api/mapping/delta-manifest",
    "/api/mapping/deltas"
  )

  foreach ($Suffix in $KnownSuffixes) {
    if ($Trimmed.EndsWith($Suffix, [System.StringComparison]::OrdinalIgnoreCase)) {
      return $Trimmed.Substring(0, $Trimmed.Length - $Suffix.Length)
    }
  }

  return $Trimmed
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ResolvedReleaseDir = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $ReleaseDir))
$TrimmedBaseUrl = Get-NormalizedBaseUrl -Url $BaseUrl

if (-not (Test-Path -LiteralPath $ResolvedReleaseDir)) {
  New-Item -ItemType Directory -Path $ResolvedReleaseDir -Force | Out-Null
}

$GlobalReleaseRoot = Split-Path -Parent $ResolvedReleaseDir
if (-not $GlobalReleaseRoot) {
  $GlobalReleaseRoot = $ResolvedReleaseDir
}

$ExistingDeltaFiles = @()
if (Test-Path -LiteralPath $GlobalReleaseRoot) {
  $ExistingDeltaFiles = Get-ChildItem -LiteralPath $GlobalReleaseRoot -Filter "delta-*.json" -File -Recurse -ErrorAction SilentlyContinue
}

$VersionNumbers = @()
foreach ($File in $ExistingDeltaFiles) {
  if ($File.BaseName -match '^delta-(\d+)$') {
    $VersionNumbers += [int]$Matches[1]
  }
}

if ($VersionNumbers.Count -gt 0) {
  $PreviousDeltaVersion = ($VersionNumbers | Measure-Object -Maximum).Maximum
  $DeltaVersion = $PreviousDeltaVersion + 1
}
else {
  $PreviousDeltaVersion = 0
  $DeltaVersion = 1
}

$PrepareScript = Join-Path $RepoRoot "tools\prepare_mapping_delta_release.py"
$PythonArgs = @(
  $PrepareScript
) + $LabeledInputs + @(
  "--base-version", "$BaseVersion",
  "--delta-version", "$DeltaVersion",
  "--previous-delta-version", "$PreviousDeltaVersion",
  "--release-dir", $ResolvedReleaseDir
)

Write-Host "Preparing mapping delta release..."
Write-Host "BaseVersion: $BaseVersion"
Write-Host "GlobalReleaseRoot: $GlobalReleaseRoot"
Write-Host "PreviousDeltaVersion: $PreviousDeltaVersion"
Write-Host "DeltaVersion: $DeltaVersion"
python @PythonArgs
if ($LASTEXITCODE -ne 0) {
  throw "prepare_mapping_delta_release.py failed with exit code $LASTEXITCODE"
}

$DeltaPath = Join-Path $ResolvedReleaseDir ("delta-{0}.json" -f $DeltaVersion)
if (-not (Test-Path -LiteralPath $DeltaPath)) {
  throw "Delta file not found: $DeltaPath"
}

$PublishUrl = "$TrimmedBaseUrl/api/admin/mapping/publish-delta"
$DeltaBody = Get-Content -LiteralPath $DeltaPath -Raw

Write-Host "Publishing delta to CloudBase..."
Invoke-RestMethod `
  -Method Post `
  -Uri $PublishUrl `
  -Headers @{ Authorization = "Bearer $AdminToken" } `
  -ContentType "application/json; charset=utf-8" `
  -Body $DeltaBody | Out-Host

$MarkUrl = "$TrimmedBaseUrl/api/admin/unknown-song/mark-exported"
$MarkBody = @{ status = $MarkExportedStatus } | ConvertTo-Json

Write-Host "Marking unknown rows as exported..."
Invoke-RestMethod `
  -Method Post `
  -Uri $MarkUrl `
  -Headers @{ Authorization = "Bearer $AdminToken" } `
  -ContentType "application/json; charset=utf-8" `
  -Body $MarkBody | Out-Host

Write-Host "Release finished."
Write-Host "Release directory: $ResolvedReleaseDir"
Write-Host "Delta file: $DeltaPath"
