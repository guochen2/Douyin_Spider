@echo off
echo 停止 DouyinLive / Redis 进程 ...
taskkill /F /IM DouyinLive.exe >nul 2>&1
for /f "tokens=2" %%p in ('tasklist /FI "IMAGENAME eq redis-server.exe" /FO LIST ^| findstr /I "PID:"') do (
    taskkill /F /PID %%p >nul 2>&1
)
timeout /t 1 /nobreak >nul
echo 完成
