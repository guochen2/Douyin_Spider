@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"
set ROOT=%CD%

echo ==============================================
echo   Douyin Live 私有化 Windows 打包 (Nuitka)
echo   - 原生编译（比 PyInstaller 更难逆向）
echo   - 内置 Redis
echo ==============================================
echo.

REM -------- 检测 Python 3.10+ --------
set PYTHON_EXE=
if exist "C:\Users\PC\.conda\envs\p310\python.exe" set "PYTHON_EXE=C:\Users\PC\.conda\envs\p310\python.exe"
if exist "C:\Users\PC\.conda\envs\np310\python.exe" set "PYTHON_EXE=C:\Users\PC\.conda\envs\np310\python.exe"
if exist "D:\ProgramData\anaconda3\envs\p310\python.exe" set "PYTHON_EXE=D:\ProgramData\anaconda3\envs\p310\python.exe"
if exist "D:\ProgramData\anaconda3\envs\np310\python.exe" set "PYTHON_EXE=D:\ProgramData\anaconda3\envs\np310\python.exe"
if exist "D:\Conda\envs\p310\python.exe" set "PYTHON_EXE=D:\Conda\envs\p310\python.exe"
if exist "D:\Conda\envs\np310\python.exe" set "PYTHON_EXE=D:\Conda\envs\np310\python.exe"

if not defined PYTHON_EXE (
    for /f "usebackq delims=" %%i in (`where python 2^>nul`) do (
        set "PYTHON_EXE=%%~i"
        goto :py_found
    )
)
:py_found

if not defined PYTHON_EXE (
    echo 错误: 未找到 Python 3.10+
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

set COMPILER_FLAG=--mingw64
where cl >nul 2>&1
if not errorlevel 1 (
    set COMPILER_FLAG=--msvc=latest
    echo 编译器: MSVC
) else (
    echo 编译器: MinGW64（本地，不联网下载）
    call scripts\setup-mingw.bat
    if errorlevel 1 goto :fail
    set "PATH=%ROOT%\tools\mingw64\bin;%PATH%"
    gcc --version
    if errorlevel 1 (
        echo 错误: MinGW gcc 不可用
        goto :fail
    )
)

echo.
echo [1/7] 安装打包依赖 ...
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements-docker.txt nuitka ordered-set zstandard
if errorlevel 1 (
    "%PYTHON_EXE%" -m pip install -r requirements-docker.txt nuitka ordered-set zstandard -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 goto :fail

"%PYTHON_EXE%" -m pip uninstall -y chardet 2>nul
"%PYTHON_EXE%" -m pip install --force-reinstall requests==2.32.3 urllib3==2.2.3 charset-normalizer==3.4.1
if errorlevel 1 (
    "%PYTHON_EXE%" -m pip install --force-reinstall requests==2.32.3 urllib3==2.2.3 charset-normalizer==3.4.1 -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo.
echo [2/7] 安装 Node.js 依赖（jsrsasign）...
if not exist node_modules\jsrsasign (
    call npm install jsrsasign --omit=dev
    if errorlevel 1 goto :fail
)

echo.
echo [3/7] 下载内置 Redis ...
call scripts\download-redis-windows.bat
if errorlevel 1 (
    if not exist tools\redis\redis-server.exe goto :fail
)

echo.
echo [4/7] 停止旧进程并清理 ...
call scripts\stop-services.bat
if exist dist\DouyinLive rmdir /s /q dist\DouyinLive 2>nul
if exist build\nuitka rmdir /s /q build\nuitka 2>nul
mkdir build\nuitka 2>nul
mkdir dist 2>nul

echo.
echo [5/7] Nuitka 编译（首次较慢，约 5-15 分钟）...
"%PYTHON_EXE%" -m nuitka ^
  --standalone ^
  %COMPILER_FLAG% ^
  --output-dir=build\nuitka ^
  --output-filename=DouyinLive.exe ^
  --windows-console-mode=disable ^
  --enable-plugin=tk-inter ^
  --include-package=dy_live ^
  --include-package=utils ^
  --include-module=utils.launcher_gui ^
  --include-module=utils.redis_config ^
  --include-package=builder ^
  --include-package=dy_apis ^
  --include-module=static.Live_pb2 ^
  --include-module=static.Response_pb2 ^
  --include-module=static.Request_pb2 ^
  --include-package=redis ^
  --include-package=websocket ^
  --include-package=google.protobuf ^
  --include-module=google.protobuf.message ^
  --include-package=execjs ^
  --include-package=bs4 ^
  --include-package=requests ^
  --include-package=charset_normalizer ^
  --include-package=urllib3 ^
  --include-package=certifi ^
  --include-package=idna ^
  --include-module=protobuf_to_dict ^
  --include-data-dir=static=static ^
  --include-data-dir=node_modules/jsrsasign=node_modules/jsrsasign ^
  --include-data-dir=config=config ^
  --nofollow-import-to=playwright ^
  --nofollow-import-to=gradio ^
  --nofollow-import-to=main ^
  --nofollow-import-to=dy_apis.login_api ^
  --nofollow-import-to=utils.cookie_util ^
  --nofollow-import-to=utils.data_util ^
  launcher.py

if errorlevel 1 goto :fail

set NUITKA_DIST=
if exist build\nuitka\launcher.dist set "NUITKA_DIST=build\nuitka\launcher.dist"
if exist build\nuitka\DouyinLive.dist set "NUITKA_DIST=build\nuitka\DouyinLive.dist"
if not defined NUITKA_DIST (
    echo 错误: 未找到 Nuitka 输出目录
    dir /b build\nuitka
    goto :fail
)

echo.
echo [6/7] 组装发布目录 ...
set OUT=dist\DouyinLive
mkdir "%OUT%" 2>nul
xcopy /E /I /Y /Q "%NUITKA_DIST%\*" "%OUT%\"
mkdir "%OUT%\tools\redis" 2>nul
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
echo Douyin Live 私有化服务端 (Nuitka 编译版^)
echo.
echo 启动: start.bat 或 DouyinLive.exe
echo 停止: stop.bat
echo.
echo 说明: 本版本由 Nuitka 编译为原生机器码，逆向难度高于 PyInstaller。
echo 直播间 JS 签名仍需 Node.js（请安装 Node 18+ 并加入 PATH^）。
echo.
echo 内置 Redis: 127.0.0.1:16380  密码见窗体或 launcher_config.json
echo 控制频道: dy_live:control
) > "%OUT%\使用说明.txt"

echo.
echo ==============================================
echo           Nuitka 打包完成!
echo ==============================================
echo 输出目录: dist\DouyinLive\
echo   DouyinLive.exe   主程序（原生编译^）
echo   start.bat        推荐启动
echo   stop.bat         停止服务
echo   tools\redis\     内置 Redis
echo.
pause
exit /b 0

:fail
echo.
echo Nuitka 打包失败。
echo 若提示缺少编译器，请安装 Visual Studio Build Tools (C++^)，
echo 或保持 --mingw64 让 Nuitka 自动下载 MinGW。
echo.
pause
exit /b 1
