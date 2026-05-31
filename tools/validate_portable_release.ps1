param(
  [string]$ReleaseRoot = ".\release",
  [string]$BundleName = "Shadow-Web-Portable"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$bundleRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot (Join-Path $ReleaseRoot $BundleName)))

if (-not (Test-Path -LiteralPath $bundleRoot)) {
  throw "未找到便携包目录：$bundleRoot"
}

$requiredPaths = @(
  "Shadow Launcher.bat",
  "README.txt",
  "app",
  "data",
  "app\shadow_music_site",
  "app\shadow_music_models",
  "app\runtime",
  "app\web\dist"
)

foreach ($relativePath in $requiredPaths) {
  $target = Join-Path $bundleRoot $relativePath
  if (-not (Test-Path -LiteralPath $target)) {
    throw "便携包缺少必要路径：$relativePath"
  }
}

$nestedBundle = Join-Path $bundleRoot $BundleName
if (Test-Path -LiteralPath $nestedBundle) {
  throw "检测到嵌套重复目录：$nestedBundle"
}

$dirtyFiles = Get-ChildItem -Path (Join-Path $bundleRoot "data") -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Extension -in @(".db", ".log", ".sqlite", ".sqlite3") -or
    $_.Name -match "mapping_sync_status|mapping_delta_state|shadow_music_site\.config"
  }

if ($dirtyFiles) {
  throw ("检测到运行残留文件：" + ($dirtyFiles | Select-Object -ExpandProperty FullName | Out-String))
}

Write-Host "便携包结构校验通过：$bundleRoot"

