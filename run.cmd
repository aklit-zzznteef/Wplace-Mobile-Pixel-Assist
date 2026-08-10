@echo off
setlocal
cd /d "%~dp0"

set "BUNDLED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PYTHON%" (
  "%BUNDLED_PYTHON%" pixel_assist.py %*
  goto :finished
)

where py >nul 2>nul
if not errorlevel 1 (
  py pixel_assist.py %*
  goto :finished
)

where python >nul 2>nul
if not errorlevel 1 (
  python pixel_assist.py %*
  goto :finished
)

echo Python was not found. Install Python 3.11 or newer first.
set "APP_EXIT_CODE=1"
goto :show_result

:finished
set "APP_EXIT_CODE=%ERRORLEVEL%"

:show_result
echo.
if "%APP_EXIT_CODE%"=="0" (
  echo Pixel Mobile Assist stopped normally.
) else (
  echo Pixel Mobile Assist could not start or stopped with error code %APP_EXIT_CODE%.
  echo Read the error above. Common causes are missing Python packages,
  echo a disconnected phone, USB debugging not authorized, or port 8765 in use.
)
echo Press any key to close this window.
pause >nul
exit /b %APP_EXIT_CODE%
