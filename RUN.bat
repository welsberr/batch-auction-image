@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" goto no_install
".venv\Scripts\python.exe" "%~dp0jeff_auction_app.py"
if errorlevel 1 goto fail
exit /b 0
:no_install
echo The application environment was not found. Run INSTALL.bat in this folder.
pause
exit /b 1
:fail
echo The application stopped with an error. Read the messages above.
pause
exit /b 1
