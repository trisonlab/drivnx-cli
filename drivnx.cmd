@echo off
rem Windows launcher: lets you run `drivnx-cli\drivnx ...` before `drivnx install` has put `drivnx` on your PATH.
where py >nul 2>nul
if %errorlevel%==0 (py -3 "%~dp0drivnx" %*) else (python "%~dp0drivnx" %*)
