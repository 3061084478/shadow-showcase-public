param(
  [string]$BundleName = "Shadow-Web-Portable",
  [string]$ReleaseRoot = ".\release",
  [string]$WorkingRoot = ".\release-working",
  [string]$PythonRuntimeRoot = "",
  [string]$MappingManifestUrl = "https://shadow-unknown-prod-d9bwced9ed8d-1438208321.ap-shanghai.app.tcloudbase.com/api/mapping/delta-manifest",
  [string]$MappingDeltasUrl = "https://shadow-unknown-prod-d9bwced9ed8d-1438208321.ap-shanghai.app.tcloudbase.com/api/mapping/deltas",
  [string]$UnknownSubmitUrl = "https://shadow-unknown-prod-d9bwced9ed8d-1438208321.ap-shanghai.app.tcloudbase.com/api/unknown-song/batch-submit"
)

$ErrorActionPreference = "Stop"

function Ensure-Directory {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Test-IsWindowsAppsPython {
  param([string]$Path)
  return $Path -like "*WindowsApps*"
}

function Remove-PathRobust {
  param(
    [string]$Target
  )
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
  $exitCode = $LASTEXITCODE
  if ($exitCode -ge 8) {
    throw "复制目录失败：$Source -> $Destination (robocopy exit code $exitCode)"
  }
}

function Copy-FileIfExists {
  param(
    [string]$Source,
    [string]$Destination
  )
  if (-not (Test-Path -LiteralPath $Source)) {
    return
  }
  $destinationDir = Split-Path -Parent $Destination
  Ensure-Directory -Path $destinationDir
  Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-FilesByPatterns {
  param(
    [string]$SourceRoot,
    [string]$DestinationRoot,
    [string[]]$Patterns
  )
  Ensure-Directory -Path $DestinationRoot
  foreach ($pattern in $Patterns) {
    foreach ($file in Get-ChildItem -LiteralPath $SourceRoot -File -Filter $pattern -ErrorAction SilentlyContinue) {
      Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $DestinationRoot $file.Name) -Force
    }
  }
}

function Trim-PythonRuntime {
  param([string]$RuntimeRoot)

  $removeDirs = @("conda-meta", "condabin", "envs", "pkgs", "share", "Menu", "Tools", "include", "libs", "shell", "etc")
  foreach ($name in $removeDirs) {
    Remove-PathRobust -Target (Join-Path $RuntimeRoot $name)
  }

  $libraryRoot = Join-Path $RuntimeRoot "Library"
  if (Test-Path -LiteralPath $libraryRoot) {
    foreach ($child in Get-ChildItem -LiteralPath $libraryRoot -Force) {
      if ($child.Name -ne "bin") {
        Remove-PathRobust -Target $child.FullName
      }
    }
    $libraryBin = Join-Path $libraryRoot "bin"
    if (Test-Path -LiteralPath $libraryBin) {
      $keepLibraryBinPatterns = @(
        "libssl-3-x64.dll",
        "libcrypto-3-x64.dll",
        "sqlite3.dll",
        "libbz2.dll",
        "liblzma.dll",
        "zlib.dll",
        "zlib-ng2.dll",
        "expat.dll",
        "libexpat.dll",
        "ffi-7.dll",
        "ffi-8.dll",
        "ffi.dll"
      )
      foreach ($child in Get-ChildItem -LiteralPath $libraryBin -Force) {
        $keep = $false
        foreach ($pattern in $keepLibraryBinPatterns) {
          if ($child.Name -ieq $pattern) {
            $keep = $true
            break
          }
        }
        if (-not $keep) {
          if ($child.PSIsContainer) {
            Remove-PathRobust -Target $child.FullName
          } else {
            Remove-Item -LiteralPath $child.FullName -Force -ErrorAction SilentlyContinue
          }
        }
      }
    }
  }

  $dllRoot = Join-Path $RuntimeRoot "DLLs"
  if (Test-Path -LiteralPath $dllRoot) {
    $keepDllNames = @(
      "_asyncio.pyd",
      "_bz2.pyd",
      "_ctypes.pyd",
      "_decimal.pyd",
      "_elementtree.pyd",
      "_hashlib.pyd",
      "_lzma.pyd",
      "_multiprocessing.pyd",
      "_overlapped.pyd",
      "_queue.pyd",
      "_socket.pyd",
      "_sqlite3.pyd",
      "_ssl.pyd",
      "_uuid.pyd",
      "_zoneinfo.pyd",
      "pyexpat.pyd",
      "select.pyd",
      "unicodedata.pyd"
    )
    foreach ($child in Get-ChildItem -LiteralPath $dllRoot -Force) {
      if ($keepDllNames -notcontains $child.Name) {
        Remove-Item -LiteralPath $child.FullName -Force -ErrorAction SilentlyContinue
      }
    }
  }

  $sitePackages = Join-Path $RuntimeRoot "Lib\site-packages"
  if (Test-Path -LiteralPath $sitePackages) {
    $keep = @(
      "requests",
      "requests-2.32.3.dist-info",
      "urllib3",
      "urllib3-2.6.3.dist-info",
      "certifi",
      "certifi-2026.2.25.dist-info",
      "charset_normalizer",
      "charset_normalizer-3.3.2.dist-info",
      "idna",
      "idna-3.7.dist-info",
      "chardet",
      "chardet-7.4.3.dist-info"
    )
    foreach ($child in Get-ChildItem -LiteralPath $sitePackages -Force) {
      if ($child.PSIsContainer -and ($keep -notcontains $child.Name)) {
        Remove-PathRobust -Target $child.FullName
      } elseif (-not $child.PSIsContainer -and $child.Name -ne "requests_file.py") {
        Remove-Item -LiteralPath $child.FullName -Force -ErrorAction SilentlyContinue
      }
    }
  }

  $removeFiles = @("_conda.exe", ".condarc", "cwp.py", "pylupdate5.bat", "pyrcc5.bat", "pyuic5.bat", "xlwings32-0.32.1.dll", "xlwings64-0.32.1.dll")
  foreach ($name in $removeFiles) {
    $target = Join-Path $RuntimeRoot $name
    if (Test-Path -LiteralPath $target) {
      Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
    }
  }

  $removeRuntimePaths = @(
    "Scripts",
    "Lib\venv",
    "Lib\idlelib",
    "Lib\test",
    "Lib\turtledemo"
  )
  foreach ($relativePath in $removeRuntimePaths) {
    Remove-PathRobust -Target (Join-Path $RuntimeRoot $relativePath)
  }
}

function Trim-NeteaseApiRuntime {
  param([string]$ApiRoot)

  $removePaths = @(
    "README.MD",
    "LICENSE",
    "interface.d.ts",
    "generateConfig.js",
    "public\docs",
    "public\audio_match_demo",
    "public\api.html",
    "public\avatar_update.html",
    "public\cloud.html",
    "public\eapi_decrypt.html",
    "public\listen_together_host.html",
    "public\playlist_cover_update.html",
    "public\playlist_import.html",
    "public\voice_upload.html",
    "data\deviceid.txt"
  )

  foreach ($relativePath in $removePaths) {
    $target = Join-Path $ApiRoot $relativePath
    if (Test-Path -LiteralPath $target) {
      if ((Get-Item -LiteralPath $target).PSIsContainer) {
        Remove-PathRobust -Target $target
      } else {
        Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
      }
    }
  }
}

function Copy-PythonRuntimeMinimal {
  param(
    [string]$SourceRoot,
    [string]$DestinationRoot
  )

  Ensure-Directory -Path $DestinationRoot

  $rootFilePatterns = @(
    "python.exe",
    "python3.dll",
    "python312.dll",
    "vcruntime*.dll",
    "msvcp*.dll",
    "ucrtbase.dll",
    "concrt140.dll",
    "vccorlib140.dll",
    "vcamp140.dll",
    "vcomp140.dll",
    "api-ms-win-*.dll",
    "zlib.dll"
  )
  Copy-FilesByPatterns -SourceRoot $SourceRoot -DestinationRoot $DestinationRoot -Patterns $rootFilePatterns

  $sourceLib = Join-Path $SourceRoot "Lib"
  $destinationLib = Join-Path $DestinationRoot "Lib"
  $excludedLibDirs = @(
    (Join-Path $sourceLib "site-packages"),
    (Join-Path $sourceLib "test"),
    (Join-Path $sourceLib "tkinter"),
    (Join-Path $sourceLib "turtledemo"),
    (Join-Path $sourceLib "venv"),
    (Join-Path $sourceLib "idlelib"),
    (Join-Path $sourceLib "ensurepip"),
    (Join-Path $sourceLib "__pycache__")
  )
  Copy-Directory -Source $sourceLib -Destination $destinationLib -ExcludeDirectories $excludedLibDirs

  $sourceSitePackages = Join-Path $sourceLib "site-packages"
  $destinationSitePackages = Join-Path $destinationLib "site-packages"
  Ensure-Directory -Path $destinationSitePackages
  $keepSitePackageEntries = @(
    "requests",
    "requests-2.32.3.dist-info",
    "urllib3",
    "urllib3-2.6.3.dist-info",
    "certifi",
    "certifi-2026.2.25.dist-info",
    "charset_normalizer",
    "charset_normalizer-3.3.2.dist-info",
    "idna",
    "idna-3.7.dist-info",
    "chardet",
    "chardet-7.4.3.dist-info",
    "requests_file.py"
  )
  foreach ($entry in $keepSitePackageEntries) {
    $sourceEntry = Join-Path $sourceSitePackages $entry
    $destinationEntry = Join-Path $destinationSitePackages $entry
    if (Test-Path -LiteralPath $sourceEntry) {
      if ((Get-Item -LiteralPath $sourceEntry).PSIsContainer) {
        Copy-Directory -Source $sourceEntry -Destination $destinationEntry -ExcludeDirectories @("__pycache__")
      } else {
        Copy-FileIfExists -Source $sourceEntry -Destination $destinationEntry
      }
    }
  }

  $sourceDlls = Join-Path $SourceRoot "DLLs"
  $destinationDlls = Join-Path $DestinationRoot "DLLs"
  Ensure-Directory -Path $destinationDlls
  $keepDllNames = @(
    "_asyncio.pyd",
    "_bz2.pyd",
    "_ctypes.pyd",
    "_decimal.pyd",
    "_elementtree.pyd",
    "_hashlib.pyd",
    "_lzma.pyd",
    "_multiprocessing.pyd",
    "_overlapped.pyd",
    "_queue.pyd",
    "_socket.pyd",
    "_sqlite3.pyd",
    "_ssl.pyd",
    "_uuid.pyd",
    "_zoneinfo.pyd",
    "pyexpat.pyd",
    "select.pyd",
    "unicodedata.pyd"
  )
  foreach ($name in $keepDllNames) {
    Copy-FileIfExists -Source (Join-Path $sourceDlls $name) -Destination (Join-Path $destinationDlls $name)
  }

  $sourceLibraryBin = Join-Path $SourceRoot "Library\bin"
  $destinationLibraryBin = Join-Path $DestinationRoot "Library\bin"
  Ensure-Directory -Path $destinationLibraryBin
  $keepLibraryBinNames = @(
    "libssl-3-x64.dll",
    "libcrypto-3-x64.dll",
    "sqlite3.dll",
    "libbz2.dll",
    "liblzma.dll",
    "zlib.dll",
    "zlib-ng2.dll",
    "expat.dll",
    "libexpat.dll",
    "ffi-7.dll",
    "ffi-8.dll",
    "ffi.dll"
  )
  foreach ($name in $keepLibraryBinNames) {
    Copy-FileIfExists -Source (Join-Path $sourceLibraryBin $name) -Destination (Join-Path $destinationLibraryBin $name)
  }
}

$repoRoot = (Resolve-Path ".").Path
$releaseRootAbs = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ReleaseRoot))
$workingRootAbs = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $WorkingRoot))
$bundleRoot = Join-Path $releaseRootAbs $BundleName
$zipPath = Join-Path $releaseRootAbs ("{0}.zip" -f $BundleName)
$stagingRoot = Join-Path $workingRootAbs $BundleName

Ensure-Directory -Path $releaseRootAbs
Ensure-Directory -Path $workingRootAbs

$frontendRoot = Join-Path $repoRoot "shadow (2)"
$frontendDist = Join-Path $frontendRoot "dist"
$backendRoot = Join-Path $repoRoot "shadow_music_site"
$modelsRoot = Join-Path $repoRoot "shadow_music_models"
$runtimeSource = Join-Path $repoRoot "V5\runtime\NeteaseCloudMusicApi"
$readmeTemplate = Join-Path $repoRoot "portable\README.customer.txt"
$launcherTemplate = Join-Path $repoRoot "portable\Shadow Launcher.bat"

if (-not (Test-Path -LiteralPath $frontendDist)) {
  throw "未找到前端 dist，请先在 shadow (2) 下执行 npm run build。"
}
if (-not (Test-Path -LiteralPath $runtimeSource)) {
  throw "未找到 V5\runtime\NeteaseCloudMusicApi，无法打入便携运行时。"
}
if (-not (Test-Path -LiteralPath $readmeTemplate)) {
  throw "未找到 portable\README.customer.txt 模板。"
}
if (-not (Test-Path -LiteralPath $launcherTemplate)) {
  throw "未找到 portable\Shadow Launcher.bat 模板。"
}

if (-not $PythonRuntimeRoot) {
  $pythonBasePrefix = python -c "import sys; print(sys.base_prefix)"
  if (-not $pythonBasePrefix) {
    throw "无法自动解析当前 Python 运行时路径，请手动传入 -PythonRuntimeRoot。"
  }
  $PythonRuntimeRoot = $pythonBasePrefix.Trim()
}

if (-not (Test-Path -LiteralPath $PythonRuntimeRoot)) {
  throw "PythonRuntimeRoot 不存在：$PythonRuntimeRoot"
}
if (Test-IsWindowsAppsPython -Path $PythonRuntimeRoot) {
  throw "当前自动检测到的是 Windows Store Python 运行时，系统文件常被占用，不适合作为便携包内置运行时。请准备一份可独立复制的 Python 目录，并通过 -PythonRuntimeRoot 显式传入。"
}

Remove-PathRobust -Target $stagingRoot
Remove-PathRobust -Target $bundleRoot
if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $stagingRoot) {
  throw "工作目录未能清空：$stagingRoot"
}
if (Test-Path -LiteralPath $bundleRoot) {
  throw "发布目录未能清空：$bundleRoot。请关闭正在占用便携包目录的进程后重试。"
}
if (Test-Path -LiteralPath $zipPath) {
  throw "旧压缩包未能删除：$zipPath"
}

Ensure-Directory -Path $stagingRoot
Ensure-Directory -Path (Join-Path $stagingRoot "app")
Ensure-Directory -Path (Join-Path $stagingRoot "app\web\dist")
Ensure-Directory -Path (Join-Path $stagingRoot "app\runtime")
Ensure-Directory -Path (Join-Path $stagingRoot "data\config")
Ensure-Directory -Path (Join-Path $stagingRoot "data\archive")
Ensure-Directory -Path (Join-Path $stagingRoot "data\outputs")
Ensure-Directory -Path (Join-Path $stagingRoot "data\tmp")
Ensure-Directory -Path (Join-Path $stagingRoot "data\npm_cache")
Ensure-Directory -Path (Join-Path $stagingRoot "data\logs")

Copy-Directory -Source $backendRoot -Destination (Join-Path $stagingRoot "app\shadow_music_site") -ExcludeDirectories @("__pycache__", "data")
Copy-Directory -Source $modelsRoot -Destination (Join-Path $stagingRoot "app\shadow_music_models") -ExcludeDirectories @("__pycache__", "collectors", "scripts", "data\raw", "data\tmp", "data\outputs", "envs") -ExcludeFiles @("config.json")
Copy-Directory -Source $frontendDist -Destination (Join-Path $stagingRoot "app\web\dist")
Copy-Directory -Source $runtimeSource -Destination (Join-Path $stagingRoot "app\runtime\NeteaseCloudMusicApi")
Copy-PythonRuntimeMinimal -SourceRoot $PythonRuntimeRoot -DestinationRoot (Join-Path $stagingRoot "app\runtime\python")
Trim-PythonRuntime -RuntimeRoot (Join-Path $stagingRoot "app\runtime\python")
Trim-NeteaseApiRuntime -ApiRoot (Join-Path $stagingRoot "app\runtime\NeteaseCloudMusicApi")

$sensitivePaths = @(
  "app\shadow_music_site\config.json",
  "app\shadow_music_site\data",
  "app\shadow_music_models\config.json",
  "app\shadow_music_models\data\raw",
  "app\shadow_music_models\data\tmp",
  "app\shadow_music_models\data\outputs",
  "app\shadow_music_models\data\processed",
  "app\shadow_music_models\scripts",
  "app\shadow_music_models\collectors",
  "app\shadow_music_site\__pycache__",
  "app\shadow_music_models\__pycache__"
)

foreach ($relativePath in $sensitivePaths) {
  $target = Join-Path $stagingRoot $relativePath
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

$singleSensitiveFiles = @(
  "app\shadow_music_site\config.json"
)
foreach ($relativePath in $singleSensitiveFiles) {
  $target = Join-Path $stagingRoot $relativePath
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Force
  }
}

$runtimeOnlyCleanupPaths = @(
  "app\shadow_music_models\model_2_playlist_analyzer",
  "app\shadow_music_models\account_playlists.py",
  "app\shadow_music_models\runtime_assessment.py",
  "app\shadow_music_models\startup_bootstrap.py"
)
foreach ($relativePath in $runtimeOnlyCleanupPaths) {
  $target = Join-Path $stagingRoot $relativePath
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

Get-ChildItem -Path $stagingRoot -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $stagingRoot -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force

$siteConfigTemplatePath = Join-Path $stagingRoot "app\shadow_music_site\config.template.json"
$siteConfigTemplate = Get-Content -LiteralPath $siteConfigTemplatePath -Raw | ConvertFrom-Json
$siteConfigTemplate.cookie = ""
$siteConfigTemplate.allow_unknown_song_contribution = $false
$siteConfigTemplate.mapping_auto_update_enabled = [bool]($MappingManifestUrl -or $MappingDeltasUrl)
$siteConfigTemplate.mapping_manifest_url = $MappingManifestUrl
$siteConfigTemplate.mapping_deltas_url = $MappingDeltasUrl
$siteConfigTemplate.unknown_song_submit_url = $UnknownSubmitUrl
$siteConfigTemplate.unknown_song_admin_token = ""
$siteConfigTemplate | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $siteConfigTemplatePath -Encoding UTF8

$modelsConfigTemplatePath = Join-Path $stagingRoot "app\shadow_music_models\config.template.json"
if (Test-Path -LiteralPath $modelsConfigTemplatePath) {
  $modelsTemplate = Get-Content -LiteralPath $modelsConfigTemplatePath -Raw | ConvertFrom-Json
  if ($modelsTemplate.PSObject.Properties.Name -contains "cookie") {
    $modelsTemplate.cookie = ""
  }
  $modelsTemplate | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $modelsConfigTemplatePath -Encoding UTF8
}

Copy-Item -LiteralPath $readmeTemplate -Destination (Join-Path $stagingRoot "README.txt") -Force
Copy-Item -LiteralPath $launcherTemplate -Destination (Join-Path $stagingRoot "Shadow Launcher.bat") -Force

$backendLauncherPath = Join-Path $stagingRoot "app\runtime\start_shadow_backend.cmd"
@(
  "@echo off",
  "setlocal",
  "",
  "set ""BUNDLE_ROOT=%~dp0..\..""",
  "for %%I in (""%BUNDLE_ROOT%"") do set ""BUNDLE_ROOT=%%~fI\""",
  "",
  "cd /d ""%BUNDLE_ROOT%app""",
  "",
  "set ""SHADOW_APP_ROOT=%BUNDLE_ROOT%app""",
  "set ""SHADOW_DATA_ROOT=%BUNDLE_ROOT%data""",
  "set ""SHADOW_CONFIG_PATH=%BUNDLE_ROOT%data\config\shadow_music_site.config.json""",
  "set ""PYTHONPATH=%BUNDLE_ROOT%app""",
  "set ""TEMP=%BUNDLE_ROOT%data\tmp""",
  "set ""TMP=%BUNDLE_ROOT%data\tmp""",
  "set ""TMPDIR=%BUNDLE_ROOT%data\tmp""",
  "set ""NPM_CONFIG_CACHE=%BUNDLE_ROOT%data\npm_cache""",
  "set ""PYTHONPYCACHEPREFIX=%BUNDLE_ROOT%data\tmp\pycache""",
  "",
  """%BUNDLE_ROOT%app\runtime\python\python.exe"" -m shadow_music_site.main >> ""%BUNDLE_ROOT%data\logs\shadow_backend.log"" 2>&1",
  "",
  "endlocal"
) | Set-Content -LiteralPath $backendLauncherPath -Encoding ASCII

Move-Item -LiteralPath $stagingRoot -Destination $bundleRoot -Force
& tar -a -cf $zipPath -C $releaseRootAbs $BundleName
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zipPath) -or ((Get-Item -LiteralPath $zipPath).Length -le 0)) {
  throw "压缩便携包失败：$zipPath"
}

Write-Host "用户便携包已生成：$bundleRoot"
Write-Host "压缩包已生成：$zipPath"
