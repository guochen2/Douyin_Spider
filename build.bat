@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"
set ROOT=%CD%

echo ==============================================
echo   Douyin Live 私有化 Windows 打包
echo   - 内置 Redis
echo   - PyArmor 代码加密
echo   - PyInstaller 可执行文件
echo ==============================================
echo.

REM -------- Python 环境（优先 conda np310 / p310，否则当前 python）--------
set PYTHON_EXE=
if exist "C:\Users\PC\.conda\envs\p310\python.exe" set "PYTHON_EXE=C:\Users\PC\.conda\envs\p310\python.exe"
if exist "C:\Users\PC\.conda\envs\np310\python.exe" set "PYTHON_EXE=C:\Users\PC\.conda\envs\np310\python.exe"
if exist "D:\ProgramData\anaconda3\envs\np310\python.exe" set "PYTHON_EXE=D:\ProgramData\anaconda3\envs\np310\python.exe"
if exist "D:\ProgramData\anaconda3\envs\p310\python.exe" set "PYTHON_EXE=D:\ProgramData\anaconda3\envs\p310\python.exe"
if exist "D:\Conda\envs\np310\python.exe" set "PYTHON_EXE=D:\Conda\envs\np310\python.exe"
if exist "D:\Conda\envs\p310\python.exe" set "PYTHON_EXE=D:\Conda\envs\p310\python.exe"
if not defined PYTHON_EXE (
    for /f "usebackq delims=" %%i in (`where python 2^>nul`) do (
        set "PYTHON_EXE=%%~i"
        goto :py_found
    )
)
:py_found
if not defined PYTHON_EXE (
    echo 错误: 未找到 Python，请安装 Python 3.10 或配置 conda 环境 np310
    pause
    exit /b 1
)
echo 使用 Python: %PYTHON_EXE%
"%PYTHON_EXE%" -c "import sys; assert sys.version_info>=(3,10), f'需要 Python 3.10+，当前 {sys.version}'"
if errorlevel 1 (
    echo 错误: 打包需要 Python 3.10 及以上
    pause
    exit /b 1
)

for %%F in ("%PYTHON_EXE%") do set "PYDIR=%%~dpF"
set "PYDIR=%PYDIR:~0,-1%"
set "PATH=%PYDIR%;%PYDIR%\Scripts;%PYDIR%\Library\bin;%PATH%"

echo.
echo [1/7] 安装打包依赖 ...
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements-docker.txt pyinstaller pyarmor
if errorlevel 1 (
    echo 尝试使用清华镜像源 ...
    "%PYTHON_EXE%" -m pip install -r requirements-docker.txt pyinstaller pyarmor -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 goto :fail

echo 对齐 requests 依赖版本 ...
"%PYTHON_EXE%" -m pip uninstall -y chardet 2>nul
"%PYTHON_EXE%" -m pip install --force-reinstall requests==2.32.3 urllib3==2.2.3 charset-normalizer==3.4.1
if errorlevel 1 (
    "%PYTHON_EXE%" -m pip install --force-reinstall requests==2.32.3 urllib3==2.2.3 charset-normalizer==3.4.1 -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo.
echo [2/7] 安装 Node.js 依赖（jsrsasign）...
if not exist node_modules\jsrsasign (
    call npm install jsrsasign --omit=dev
    if %errorlevel% neq 0 goto :fail
)

echo.
echo [3/7] 下载内置 Redis ...
call scripts\download-redis-windows.bat
if %errorlevel% neq 0 (
    if exist tools\redis\redis-server.exe (
        echo [redis] 检测到手动放置的 redis-server.exe，继续打包 ...
    ) else (
        goto :fail
    )
)

echo.
echo [4/7] 准备打包源码（尝试 PyArmor 加密）...
if exist build\obf rmdir /s /q build\obf
mkdir build\obf

set OBF=0
if /I not "%SKIP_PYARMOR%"=="1" (
    echo 尝试加密核心文件（试用版有文件大小/数量限制）...
    pyarmor gen -O build\obf --mix-str launcher.py dy_live\live_manager.py dy_live\server.py utils\dy_util.py
    if !errorlevel! equ 0 (
        set OBF=1
        echo PyArmor 加密成功
        xcopy /E /I /Y /Q builder build\obf\builder
        xcopy /E /I /Y /Q dy_apis build\obf\dy_apis
        for %%f in (redis_util.py redis_bootstrap.py console_util.py common_util.py cookie_util.py data_util.py app_bootstrap.py __init__.py) do (
            if exist utils\%%f copy /Y utils\%%f build\obf\utils\%%f >nul
        )
        if not exist build\obf\dy_live\runtime_hook.py copy /Y dy_live\runtime_hook.py build\obf\dy_live\ >nul
        if not exist build\obf\dy_live\__init__.py copy /Y dy_live\__init__.py build\obf\dy_live\ >nul
    ) else (
        echo PyArmor 加密失败（常见原因: 试用版 out of license^）
    )
)

if "%OBF%"=="0" (
    echo 使用源码直接打包（未加密，功能不受影响^）
    copy /Y launcher.py build\obf\ >nul
    xcopy /E /I /Y /Q dy_live build\obf\dy_live
    xcopy /E /I /Y /Q utils build\obf\utils
    xcopy /E /I /Y /Q builder build\obf\builder
    xcopy /E /I /Y /Q dy_apis build\obf\dy_apis
)

echo.
echo [5/7] 复制静态资源到加密目录 ...
xcopy /E /I /Y /Q static build\obf\static
mkdir build\obf\config 2>nul
copy /Y config\redis.conf build\obf\config\ >nul
mkdir build\obf\node_modules 2>nul
xcopy /E /I /Y /Q node_modules\jsrsasign build\obf\node_modules\jsrsasign
if not exist build\obf\dy_live\runtime_hook.py copy /Y dy_live\runtime_hook.py build\obf\dy_live\ >nul

echo.
echo [6/7] PyInstaller 打包 ...
call scripts\stop-services.bat
if exist dist\DouyinLive (
    rmdir /s /q dist\DouyinLive 2>nul
    if exist dist\DouyinLive (
        echo 无法删除 dist\DouyinLive，请先关闭 DouyinLive.exe 后重试
        goto :fail
    )
)
mkdir dist 2>nul
cd build\obf
pyinstaller --clean --noconfirm ..\..\packaging\launcher-windows.spec --distpath ..\..\dist --workpath ..\..\build\pyinstaller
if %errorlevel% neq 0 (
    cd /d "%ROOT%"
    goto :fail
)
cd /d "%ROOT%"

echo.
echo [7/7] 组装发布目录 ...
set OUT=dist\DouyinLive
mkdir "%OUT%\tools\redis" 2>nul
mkdir "%OUT%\config" 2>nul
xcopy /E /I /Y /Q tools\redis\*.exe "%OUT%\tools\redis\"
copy /Y config\redis.conf "%OUT%\config\" >nul
copy /Y packaging\start.bat "%OUT%\start.bat" >nul
copy /Y scripts\stop-services.bat "%OUT%\stop.bat" >nul
if not exist "%OUT%\launcher_config.json" (
    echo {"embedded_redis": true, "redis_port": 16380, "redis_control_channel": "dy_live:control"}> "%OUT%\launcher_config.json"
) else (
    copy /Y launcher_config.json "%OUT%\launcher_config.json" >nul
)

(
echo Douyin Live 私有化服务端
echo.
echo 启动: 双击 start.bat 或 DouyinLive.exe
echo 停止: 双击 stop.bat（重新打包前请先停止）
echo.
echo 内置 Redis 默认:
echo   地址: 127.0.0.1:16380
echo   密码: 首次启动自动生成 12 位，可在窗体中修改
echo   控制频道: dy_live:control
echo.
echo 使用外部 Redis 时，设置环境变量 REDIS_HOST 或在 launcher_config.json 中设置:
echo   "embedded_redis": false
echo.
echo 控制消息格式:
echo   {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}
) > "%OUT%\使用说明.txt"

echo.
echo ==============================================
echo              打包完成!
echo ==============================================
echo 输出目录: dist\DouyinLive\
echo   start.bat            推荐启动
if "%OBF%"=="1" (
echo   DouyinLive.exe       主程序（PyArmor 已加密核心代码^）
) else (
echo   DouyinLive.exe       主程序（未加密，试用版额度不足时可正常分发^）
)
echo   tools\redis\         内置 Redis
echo   launcher_config.json 配置文件
echo   使用说明.txt
echo.
echo 将整个 DouyinLive 文件夹复制到目标 Windows 机器即可运行。
echo.
pause
exit /b 0

:fail
echo.
echo 打包失败，请检查上方错误信息。
pause
exit /b 1
