param(
  [string]$DestinationRoot = ".\shadow-showcase-public"
)

$ErrorActionPreference = "Stop"

function Ensure-Directory {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Remove-PathRobust {
  param([string]$Target)
  if (-not (Test-Path -LiteralPath $Target)) {
    return
  }
  cmd /c rmdir /s /q "$Target" 2>$null | Out-Null
  if (Test-Path -LiteralPath $Target) {
    Remove-Item -LiteralPath $Target -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Copy-Directory {
  param(
    [string]$Source,
    [string]$Destination,
    [string[]]$ExcludeDirectories = @(),
    [string[]]$ExcludeFiles = @()
  )
  Ensure-Directory -Path $Destination
  $robocopyArgs = @(
    $Source,
    $Destination,
    "/E",
    "/NFL",
    "/NDL",
    "/NJH",
    "/NJS",
    "/NP",
    "/R:1",
    "/W:1"
  )
  if ($ExcludeDirectories.Count -gt 0) {
    $robocopyArgs += "/XD"
    $robocopyArgs += $ExcludeDirectories
  }
  if ($ExcludeFiles.Count -gt 0) {
    $robocopyArgs += "/XF"
    $robocopyArgs += $ExcludeFiles
  }
  & robocopy @robocopyArgs | Out-Null
  if ($LASTEXITCODE -ge 8) {
    throw "复制目录失败：$Source -> $Destination"
  }
}

function Copy-File {
  param(
    [string]$Source,
    [string]$Destination
  )
  $parent = Split-Path -Parent $Destination
  Ensure-Directory -Path $parent
  Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$destination = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $DestinationRoot))

Remove-PathRobust -Target $destination
Ensure-Directory -Path $destination
Ensure-Directory -Path (Join-Path $destination "docs")
Ensure-Directory -Path (Join-Path $destination "portable")
Ensure-Directory -Path (Join-Path $destination "tools")

Copy-File -Source (Join-Path $repoRoot "README.md") -Destination (Join-Path $destination "README.md")
Copy-File -Source (Join-Path $repoRoot ".gitignore") -Destination (Join-Path $destination ".gitignore")

Copy-Directory -Source (Join-Path $repoRoot "docs") -Destination (Join-Path $destination "docs")
Copy-Directory -Source (Join-Path $repoRoot "portable") -Destination (Join-Path $destination "portable")
Copy-Directory -Source (Join-Path $repoRoot "cloudbase-functions") -Destination (Join-Path $destination "cloudbase-functions") -ExcludeDirectories @("__pycache__")
Copy-Directory -Source (Join-Path $repoRoot "shadow (2)") -Destination (Join-Path $destination "shadow-web") -ExcludeDirectories @("node_modules", "dist", ".vite", "__pycache__")
Copy-Directory -Source (Join-Path $repoRoot "shadow_music_site") -Destination (Join-Path $destination "shadow_music_site") -ExcludeDirectories @("__pycache__", "data") -ExcludeFiles @("config.json")
Copy-Directory -Source (Join-Path $repoRoot "shadow_music_models") -Destination (Join-Path $destination "shadow_music_models") -ExcludeDirectories @("__pycache__", "data\\raw", "data\\tmp", "data\\outputs", "envs") -ExcludeFiles @("config.json")

$toolFiles = @(
  "build_mapping_delta.py",
  "check_labeled_against_mapping.py",
  "create_cloudbase_mapping_bundle.ps1",
  "create_shadow_web_portable_bundle.ps1",
  "export_public_showcase.ps1",
  "export_unknown_pending.ps1",
  "prepare_mapping_delta_release.py",
  "publish_mapping_delta.ps1",
  "validate_portable_release.ps1"
)
foreach ($toolFile in $toolFiles) {
  $source = Join-Path $repoRoot ("tools\" + $toolFile)
  if (Test-Path -LiteralPath $source) {
    Copy-File -Source $source -Destination (Join-Path $destination ("tools\" + $toolFile))
  }
}

$cleanupPatterns = @("*.db", "*.sqlite", "*.sqlite3", "*.log")
foreach ($pattern in $cleanupPatterns) {
  Get-ChildItem -Path $destination -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}

Get-ChildItem -Path $destination -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $destination -Recurse -Directory -Filter ".pytest_cache" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$forcedRemovePaths = @(
  "reference-docs",
  "shadow-web\.git",
  "shadow_music_models\data\raw",
  "shadow_music_models\data\tmp",
  "shadow_music_models\data\outputs",
  "shadow_music_site\data"
)
foreach ($relativePath in $forcedRemovePaths) {
  $target = Join-Path $destination $relativePath
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
  }
}

Write-Host "公开展示目录已生成：$destination"
