@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."
set ROOT=%CD%

REM 手动下载的 MinGW 压缩包路径（可按实际修改）
set "MINGW_ZIP=D:\Colin\software\winlibs-x86_64-posix-seh-gcc-15.2.0-mingw-w64msvcrt-13.0.0-r6.zip"
set "MINGW_ROOT=%ROOT%\tools\mingw64"
set "NUITKA_GCC_VER=15.2.0posix-13.0.0-msvcrt-r6"

if exist "%MINGW_ROOT%\bin\gcc.exe" (
    echo [mingw] 已存在: %MINGW_ROOT%\bin\gcc.exe
    goto :cache
)

if not exist "%MINGW_ZIP%" (
    echo [mingw] 未找到压缩包: %MINGW_ZIP%
    echo 请从以下地址下载后放到上述路径，或修改本脚本中的 MINGW_ZIP:
    echo https://github.com/brechtsanders/winlibs_mingw/releases/download/15.2.0posix-13.0.0-msvcrt-r6/winlibs-x86_64-posix-seh-gcc-15.2.0-mingw-w64msvcrt-13.0.0-r6.zip
    exit /b 1
)

echo [mingw] 解压 MinGW 到 tools\mingw64 ...
set "TMP_EXTRACT=%ROOT%\build\mingw_extract"
if exist "%TMP_EXTRACT%" rmdir /s /q "%TMP_EXTRACT%"
mkdir "%TMP_EXTRACT%" 2>nul
mkdir "%ROOT%\tools" 2>nul

powershell -NoProfile -Command "Expand-Archive -Path '%MINGW_ZIP%' -DestinationPath '%TMP_EXTRACT%' -Force"
if errorlevel 1 (
    echo [mingw] 解压失败
    exit /b 1
)

if exist "%TMP_EXTRACT%\mingw64" (
    if exist "%MINGW_ROOT%" rmdir /s /q "%MINGW_ROOT%"
    move /Y "%TMP_EXTRACT%\mingw64" "%MINGW_ROOT%" >nul
) else (
    echo [mingw] 解压后未找到 mingw64 目录
    dir /b "%TMP_EXTRACT%"
    exit /b 1
)

rmdir /s /q "%TMP_EXTRACT%" 2>nul

if not exist "%MINGW_ROOT%\bin\gcc.exe" (
    echo [mingw] 未找到 gcc.exe
    exit /b 1
)
echo [mingw] 解压完成: %MINGW_ROOT%

:cache
REM 同步到 Nuitka 缓存目录，避免运行时再次下载
set "NUITKA_CACHE=%LOCALAPPDATA%\Nuitka\Nuitka\Cache\downloads\gcc\x86_64\%NUITKA_GCC_VER%"
if not exist "%NUITKA_CACHE%\mingw64\bin\gcc.exe" (
    echo [mingw] 写入 Nuitka 缓存: %NUITKA_CACHE%
    mkdir "%NUITKA_CACHE%" 2>nul
    xcopy /E /I /Y /Q "%MINGW_ROOT%" "%NUITKA_CACHE%\mingw64\"
)

echo [mingw] 就绪
exit /b 0
