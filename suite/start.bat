@echo off
chcp 936 >nul
setlocal
title Rainy75 V2 Windows suite
cd /d "%~dp0.."

call "%~dp0..\toolbox\find_python.bat"
if errorlevel 1 goto nopython

echo Rainy75 Windows 套件
echo   打开 http://127.0.0.1:8770/suite/  （Chrome / Edge）
echo   保持这个窗口开着；按 Ctrl+C 停止。
echo.
"%PY%" %PYARGS% suite\server.py --port 8770
if not errorlevel 1 exit /b 0
echo.
echo [失败] 套件退出，请把上面的报错发给我。
pause
exit /b 1

:nopython
echo.
pause
exit /b 1
