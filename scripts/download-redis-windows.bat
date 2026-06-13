@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."
set "ROOT=%CD%"
set "REDIS_DIR=%ROOT%\tools\redis"
set "BUILD_DIR=%ROOT%\build"
set "ZIP=%BUILD_DIR%\redis-win.zip"
set "EXTRACT=%BUILD_DIR%\redis-win"
set "LOCAL_ZIP=%REDIS_DIR%\Redis-x64-5.0.14.1.zip"

if exist "%REDIS_DIR%\redis-server.exe" (
    echo [redis] 已存在: %REDIS_DIR%\redis-server.exe
    exit /b 0
)

mkdir "%BUILD_DIR%" 2>nul
mkdir "%REDIS_DIR%" 2>nul

if exist "%LOCAL_ZIP%" (
    echo [redis] 使用本地压缩包: %LOCAL_ZIP%
    copy /Y "%LOCAL_ZIP%" "%ZIP%" >nul
    goto :extract
)

if exist "%ROOT%\build\redis-win.zip" (
    echo [redis] 使用本地压缩包: build\redis-win.zip
    set "ZIP=%ROOT%\build\redis-win.zip"
    goto :extract
)

echo [redis] 正在下载 Windows 便携版 Redis（依次尝试多个镜像）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-redis-windows.ps1" -OutFile "%ZIP%"
if %errorlevel% neq 0 goto :manual

if not exist "%ZIP%" goto :manual

:extract
echo [redis] 解压 Redis ...
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACT%' -Force"
if %errorlevel% neq 0 (
    echo [redis] 解压失败
    goto :manual
)

for /r "%EXTRACT%" %%f in (redis-server.exe) do (
    copy /Y "%%f" "%REDIS_DIR%\"
    goto :found
)
:found

if not exist "%REDIS_DIR%\redis-server.exe" (
    echo [redis] 解压后未找到 redis-server.exe
    goto :manual
)

echo [redis] 已安装到 %REDIS_DIR%
exit /b 0

:manual
echo.
echo [redis] 自动下载失败，请手动安装：
echo   1. 下载 Redis-x64-5.0.14.1.zip
echo   2. 放到 %REDIS_DIR%\ 目录下
echo   3. 或将 redis-server.exe 直接放到 %REDIS_DIR%\
echo   4. 重新运行 build.bat
echo.
echo 下载地址（任选其一，浏览器打开）：
echo   https://ghfast.top/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip
echo   https://mirror.ghproxy.com/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip
echo   https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip
echo.
exit /b 1
