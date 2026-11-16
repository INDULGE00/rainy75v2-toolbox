@echo off
chcp 936 >nul
setlocal
title Rainy75 V2 Toolbox
cd /d "%~dp0"

echo.
echo  ==========================================================
echo    Rainy75 V2 工具箱  ·  刷机向导 + 主题定制台（离线）
echo  ==========================================================
echo.

call "%~dp0toolbox\find_python.bat"
if errorlevel 1 goto nopython

echo  使用解释器: %PY% %PYARGS%
echo.
"%PY%" %PYARGS% -u "toolbox\launch.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" goto failed
exit /b 0

:failed
echo.
echo  [失败] 工具箱退出，代码 %RC%
echo.
echo  常见原因：
echo    - 8766 端口被其它程序占用（关掉占用的程序再试，或加参数 --port 8770）
echo    - 缺少 Pillow：在命令行执行  pip install pillow
echo    - Python 版本太低（需要 3.9 以上）
echo.
echo  具体报错见上面的输出。
echo.
pause
exit /b %RC%

:nopython
echo.
pause
exit /b 1
