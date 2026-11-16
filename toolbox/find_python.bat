@echo off
rem 被其它启动脚本用 call 调用：  call "路径\find_python.bat"
rem 成功后设置 PY（解释器）与 PYARGS（附加参数，如 -3）；失败时 exit /b 1。
rem
rem 为什么不直接敲 python：
rem 本机 PATH 里的 python 常常只是 Microsoft Store 的“占位符”
rem （%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe）。这个文件确实存在，
rem where python 也能通过，但它不会真的执行代码 —— 于是启动脚本要么一闪就没了，
rem 要么停在“请按任意键继续”然后关窗。所以这里必须真跑一次并检查输出，
rem 不能只看文件是否存在。

set "PY="
set "PYARGS="
set "CAND="
set "CANDARGS="
set "PROBE=%TEMP%\rainy75-pyprobe.txt"

rem 1) WorkBuddy 自带的 Python（本机验证过，自带 Pillow）
for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
  if not defined PY call :probe "%%~fD\python.exe"
)

rem 2) 官方 py 启动器
if not defined PY call :probe_py

rem 3) PATH 里的 python（可能是占位符，probe 会识破）
if not defined PY call :probe_cmd python

rem 4) 常见安装位置
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if not defined PY call :probe "%%~fD\python.exe"
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
  if not defined PY call :probe "%%~fD\python.exe"
)
for /d %%D in ("C:\Python3*") do (
  if not defined PY call :probe "%%~fD\python.exe"
)

if defined PY exit /b 0

echo.
echo  [错误] 没找到可用的 Python 3（需要 3.9 以上，且已安装 Pillow）
echo.
echo  原因：PATH 里的 python 很可能是 Microsoft Store 的占位符，
echo        它不会真的运行程序，所以窗口才会一闪而过。
echo.
echo  解决办法（任选一个）：
echo    1. 到 python.org 安装 Python 3.11+，安装时勾选 "Add python.exe to PATH"，
echo       然后在该 Python 里执行：  pip install pillow
echo    2. 或者告诉我有 python.exe 的完整路径，我把启动脚本指向它。
echo.
exit /b 1

rem ---------------------------------------------------------------- 探测
:probe
set "CAND=%~1"
set "CANDARGS="
if not exist "%CAND%" exit /b 1
goto run_probe

:probe_cmd
set "CAND=%~1"
set "CANDARGS="
goto run_probe

:probe_py
set "CAND=py"
set "CANDARGS=-3"
goto run_probe

:run_probe
if exist "%PROBE%" del "%PROBE%" >nul 2>nul
"%CAND%" %CANDARGS% -c "import sys,PIL;sys.stdout.write('OK'+str(sys.version_info[0])+'.'+str(sys.version_info[1]))" >"%PROBE%" 2>nul
set "TOK="
if exist "%PROBE%" set /p TOK=<"%PROBE%"
if not defined TOK exit /b 1
if not "%TOK:~0,4%"=="OK3." exit /b 1
set "PY=%CAND%"
set "PYARGS=%CANDARGS%"
if exist "%PROBE%" del "%PROBE%" >nul 2>nul
exit /b 0
