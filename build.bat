@echo off
cls
@echo ==============================================
@echo           Douyin Live Launcher Builder
@echo ==============================================
@echo.

set PYTHON_PATH=D:\Conda\envs\np310

if not exist "%PYTHON_PATH%\python.exe" (
    @echo Error: Python environment not found
    @echo Path: %PYTHON_PATH%
    pause
    exit /b 1
)

@echo 1. Installing dependencies...
"%PYTHON_PATH%\Scripts\pip.exe" install pyinstaller pyarmor

if %errorlevel% neq 0 (
    @echo Error: Failed to install dependencies
    pause
    exit /b 1
)

@echo 2. Creating directories...
mkdir dist 2>nul
mkdir dist\launcher 2>nul
mkdir dist\server 2>nul
mkdir build 2>nul

@echo 3. Building launcher.exe...
cd /d e:\code\Douyin_Spider
set PATH=%PYTHON_PATH%;%PYTHON_PATH%\Scripts;%PYTHON_PATH%\Library\bin;%PATH%
"%PYTHON_PATH%\Scripts\pyinstaller.exe" launcher_cli.spec --distpath dist/launcher --workpath build/launcher

if %errorlevel% neq 0 (
    @echo Error: Failed to build launcher
    pause
    exit /b 1
)

@echo 4. Building server.exe (debug mode)...
cd /d e:\code\Douyin_Spider\dy_live
"%PYTHON_PATH%\Scripts\pyinstaller.exe" server_simple.spec --distpath ../dist/server --workpath ../build/server

if %errorlevel% neq 0 (
    @echo Error: Failed to build server
    pause
    exit /b 1
)

cd /d e:\code\Douyin_Spider

@echo 5. Protecting with PyArmor...
@echo Obfuscating launcher_cli.py...
"%PYTHON_PATH%\Scripts\pyarmor.exe" obfuscate --output dist/protected_launcher launcher_cli.py

@echo Obfuscating server.py...
"%PYTHON_PATH%\Scripts\pyarmor.exe" obfuscate --output dist/protected_server dy_live/server.py

@echo 6. Copying protected files...
copy dist\protected_launcher\dist\launcher.exe dist\launcher\launcher_protected.exe >nul
copy dist\protected_server\dist\server.exe dist\server\server_protected.exe >nul

@echo.
@echo ==============================================
@echo              Build Complete!
@echo ==============================================
@echo Output:
@echo   - launcher.exe: dist/launcher/
@echo   - server.exe: dist/server/
@echo   - Protected versions available
@echo.
pause