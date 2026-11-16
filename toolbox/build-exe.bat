@echo off
chcp 936 >nul
setlocal
title Build Rainy75Toolbox.exe
cd /d "%~dp0.."

call "%~dp0find_python.bat"
if errorlevel 1 goto nopython

echo.
echo  Building single-file exe with: %PY%
echo  (payload + PyInstaller, takes about 1 minute)
echo.
"%PY%" %PYARGS% "toolbox\make_exe.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" goto failed

echo.
echo  Done: dist\Rainy75Toolbox.exe
echo.
pause
exit /b 0

:failed
echo.
echo  [FAILED] exit code %RC% - see the log above.
echo  Common causes: PyInstaller missing (pip install pyinstaller),
echo  llvm-portable missing (or pass --no-clang), dist exe still running.
echo.
pause
exit /b %RC%

:nopython
echo.
pause
exit /b 1
