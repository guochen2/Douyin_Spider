@echo off
chcp 936 >nul
cd /d "%~dp0"
DouyinLive.exe
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
    echo Exit code: %ERR%
    if exist DouyinLive.error.log type DouyinLive.error.log
)
pause
