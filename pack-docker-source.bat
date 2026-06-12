@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist dist mkdir dist

set ARCHIVE=dist\douyin-spider-docker-src.tar.gz
if exist "%ARCHIVE%" del /f "%ARCHIVE%"

echo ==============================================
echo   打包 Docker 构建源码（不含 node_modules）
echo ==============================================
echo.

tar -czf "%ARCHIVE%" ^
  --exclude=node_modules ^
  --exclude=static/node_modules ^
  --exclude=.git ^
  --exclude=__pycache__ ^
  --exclude=.venv ^
  --exclude=venv ^
  --exclude=dist ^
  --exclude=build ^
  --exclude=*.exe ^
  --exclude=.env ^
  --exclude=.env* ^
  Dockerfile docker-compose.yml .dockerignore requirements-docker.txt package-docker.json ^
  launcher.py launcher_config.json ^
  build-linux.sh run-on-linux.sh ^
  builder dy_apis dy_live static utils scripts

if exist package-lock.json (
  tar -rzf "%ARCHIVE%" package-lock.json 2>nul
)

if %errorlevel% neq 0 (
  echo 打包失败，请确认 Windows 已安装 tar 命令（Win10+ 自带）
  pause
  exit /b 1
)

echo.
echo 已生成: %ARCHIVE%
echo.
echo 上传到 Linux 服务器后执行:
echo   tar -xzf douyin-spider-docker-src.tar.gz
echo   docker compose up -d --build
echo.
echo node_modules 会在 Docker 构建时自动安装，无需上传。
echo.
pause
