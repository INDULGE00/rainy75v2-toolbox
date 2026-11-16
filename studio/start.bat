@echo off
chcp 936 >nul
setlocal
title Rainy75 V2 customization studio
cd /d "%~dp0.."

call "%~dp0..\toolbox\find_python.bat"
if errorlevel 1 goto nopython

echo Rainy75 V2 主题定制台
echo   打开 http://127.0.0.1:8766/studio/  （Chrome / Edge）
echo   关闭这个窗口或按 Ctrl+C 停止服务。
echo.
"%PY%" %PYARGS% tools\studio.py --port 8766
if not errorlevel 1 exit /b 0
echo.
echo [失败] 定制台退出，请把上面的报错发给我。
pause
exit /b 1

:nopython
echo.
pause
exit /b 1
