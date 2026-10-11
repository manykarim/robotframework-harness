@echo off
rem rf-harness hook launcher for Windows shells: runs bin\rfh-launch with the first Python it finds.
rem Usage: rfh-launch.cmd ^<Event^> --agent ^<agent^>   (hook payload on stdin). Always exits 0 or 2.
setlocal
set "_RFHL=%~dp0rfh-launch"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -S "%_RFHL%" %*
  goto :done
)
where python >nul 2>nul
if not errorlevel 1 (
  python -S "%_RFHL%" %*
  goto :done
)
exit /b 0
:done
if "%ERRORLEVEL%"=="2" exit /b 2
exit /b 0
