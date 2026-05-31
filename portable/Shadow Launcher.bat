@echo off
setlocal

set "BUNDLE_ROOT=%~dp0"
cd /d "%BUNDLE_ROOT%"

set "SHADOW_APP_ROOT=%BUNDLE_ROOT%app"
set "SHADOW_DATA_ROOT=%BUNDLE_ROOT%data"
set "SHADOW_CONFIG_PATH=%BUNDLE_ROOT%data\config\shadow_music_site.config.json"
set "PYTHONPATH=%BUNDLE_ROOT%app"
set "TEMP=%BUNDLE_ROOT%data\tmp"
set "TMP=%BUNDLE_ROOT%data\tmp"
set "TMPDIR=%BUNDLE_ROOT%data\tmp"
set "NPM_CONFIG_CACHE=%BUNDLE_ROOT%data\npm_cache"
set "PYTHONPYCACHEPREFIX=%BUNDLE_ROOT%data\tmp\pycache"

if not exist "%BUNDLE_ROOT%data\config" mkdir "%BUNDLE_ROOT%data\config"
if not exist "%BUNDLE_ROOT%data\archive" mkdir "%BUNDLE_ROOT%data\archive"
if not exist "%BUNDLE_ROOT%data\outputs" mkdir "%BUNDLE_ROOT%data\outputs"
if not exist "%BUNDLE_ROOT%data\tmp" mkdir "%BUNDLE_ROOT%data\tmp"
if not exist "%BUNDLE_ROOT%data\npm_cache" mkdir "%BUNDLE_ROOT%data\npm_cache"
if not exist "%BUNDLE_ROOT%data\logs" mkdir "%BUNDLE_ROOT%data\logs"

set "NCM_API_DIR=%BUNDLE_ROOT%app\runtime\NeteaseCloudMusicApi"

pushd "%NCM_API_DIR%"
start "Shadow Local API" /min "start_api.bat"
popd

start "Shadow Backend" /min /d "%BUNDLE_ROOT%app\runtime" cmd /c start_shadow_backend.cmd

set /a SHADOW_WAIT_SECONDS=0
:wait_backend_ready
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8787/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto open_shadow
set /a SHADOW_WAIT_SECONDS+=1
if %SHADOW_WAIT_SECONDS% geq 30 goto open_shadow
timeout /t 1 /nobreak >nul
goto wait_backend_ready

:open_shadow
start "" "http://127.0.0.1:8787/"

exit /b 0

