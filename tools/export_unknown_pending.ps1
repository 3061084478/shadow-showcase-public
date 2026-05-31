param(
  [Parameter(Mandatory = $true)]
  [string]$BaseUrl,

  [Parameter(Mandatory = $true)]
  [string]$AdminToken,

  [string]$Status = "pending",

  [string]$OutputPath = ".\build\unknown-pending.json"
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

$ResolvedOutputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$ResolvedOutputDir = Split-Path -Parent $ResolvedOutputPath
if (-not (Test-Path -LiteralPath $ResolvedOutputDir)) {
  New-Item -ItemType Directory -Path $ResolvedOutputDir -Force | Out-Null
}

$TrimmedBaseUrl = Get-NormalizedBaseUrl -Url $BaseUrl
$ExportUrl = "$TrimmedBaseUrl/api/admin/unknown-song/export?status=$([uri]::EscapeDataString($Status))"

Invoke-WebRequest `
  -Uri $ExportUrl `
  -Headers @{ Authorization = "Bearer $AdminToken" } `
  -OutFile $ResolvedOutputPath

Write-Host "Unknown export saved to: $ResolvedOutputPath"
