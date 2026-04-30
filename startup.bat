@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
if "%WASA_BACKEND_PORT%"=="" set "WASA_BACKEND_PORT=8000"
if "%WASA_FRONTEND_PORT%"=="" set "WASA_FRONTEND_PORT=5173"
if "%WASA_HOST%"=="" set "WASA_HOST=127.0.0.1"

set "RUNTIME_DIR=%ROOT_DIR%\.runtime"
set "LOG_DIR=%RUNTIME_DIR%\logs"
set "BACKEND_PID_FILE=%RUNTIME_DIR%\backend.pid"
set "FRONTEND_PID_FILE=%RUNTIME_DIR%\frontend.pid"
set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"

if "%1"=="" goto usage
if /I "%1"=="start" goto start
if /I "%1"=="stop" goto stop
if /I "%1"=="restart" goto restart
if /I "%1"=="status" goto status
goto usage

:usage
echo AKReport Windows 快捷管理脚本
echo.
echo 用法:
echo   startup.bat start      启动后端和前端
echo   startup.bat stop       关闭本项目的后端和前端
echo   startup.bat restart    重启后端和前端
echo   startup.bat status     查看运行状态
echo.
echo 环境变量:
echo   WASA_BACKEND_PORT=8000
echo   WASA_FRONTEND_PORT=5173
echo   WASA_HOST=127.0.0.1
exit /b 1

:ensure_runtime
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
exit /b 0

:start
call :ensure_runtime
if not exist "%PYTHON_EXE%" (
  echo 找不到虚拟环境: %PYTHON_EXE%
  echo 请先在项目根目录创建 .venv 并安装后端依赖。
  exit /b 1
)
if not exist "%ROOT_DIR%\frontend\node_modules" (
  echo 找不到前端依赖: %ROOT_DIR%\frontend\node_modules
  echo 请先执行: cd frontend ^&^& npm install
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList '-m','uvicorn','app.main:app','--reload','--host','%WASA_HOST%','--port','%WASA_BACKEND_PORT%' -WorkingDirectory '%ROOT_DIR%\backend' -RedirectStandardOutput '%LOG_DIR%\backend.log' -RedirectStandardError '%LOG_DIR%\backend.err.log' -PassThru; $p.Id | Out-File -Encoding ascii '%BACKEND_PID_FILE%'"
echo 后端启动中，日志: %LOG_DIR%\backend.log

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev','--','--host','%WASA_HOST%','--port','%WASA_FRONTEND_PORT%','--strictPort' -WorkingDirectory '%ROOT_DIR%\frontend' -RedirectStandardOutput '%LOG_DIR%\frontend.log' -RedirectStandardError '%LOG_DIR%\frontend.err.log' -PassThru; $p.Id | Out-File -Encoding ascii '%FRONTEND_PID_FILE%'"
echo 前端启动中，日志: %LOG_DIR%\frontend.log
echo.
echo 前端地址: http://%WASA_HOST%:%WASA_FRONTEND_PORT%
echo API 文档: http://%WASA_HOST%:%WASA_BACKEND_PORT%/docs
exit /b 0

:stop
for %%F in ("%BACKEND_PID_FILE%" "%FRONTEND_PID_FILE%") do (
  if exist %%F (
    set /p PID=<%%F
    if not "!PID!"=="" (
      taskkill /PID !PID! /T /F >nul 2>nul
    )
    del %%F >nul 2>nul
  )
)
echo 已请求关闭本项目进程。
exit /b 0

:restart
call :stop
call :start
exit /b %ERRORLEVEL%

:status
echo 后端: http://%WASA_HOST%:%WASA_BACKEND_PORT%
if exist "%BACKEND_PID_FILE%" (
  set /p BACKEND_PID=<"%BACKEND_PID_FILE%"
  tasklist /FI "PID eq !BACKEND_PID!" | find "!BACKEND_PID!" >nul && echo   运行中 PID !BACKEND_PID! || echo   未运行
) else (
  echo   未运行
)
echo 前端: http://%WASA_HOST%:%WASA_FRONTEND_PORT%
if exist "%FRONTEND_PID_FILE%" (
  set /p FRONTEND_PID=<"%FRONTEND_PID_FILE%"
  tasklist /FI "PID eq !FRONTEND_PID!" | find "!FRONTEND_PID!" >nul && echo   运行中 PID !FRONTEND_PID! || echo   未运行
) else (
  echo   未运行
)
exit /b 0
