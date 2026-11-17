@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto fail
if exist ".venv\Scripts\python.exe" goto have_venv
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto no_python
py -3 -m venv .venv
if errorlevel 1 goto fail
:have_venv
echo Installing dependencies from the Python package index. Internet is required.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -c "import cv2,numpy,PIL,tkinter; print('Dependencies verified')"
if errorlevel 1 goto fail
echo Installation complete. Open RUN.bat in this folder.
pause
exit /b 0
:no_python
echo Python 3.10 or later and the Python launcher are required. Install Python with Tk support, then retry.
pause
exit /b 1
:fail
echo Installation failed. Read the messages above.
pause
exit /b 1
