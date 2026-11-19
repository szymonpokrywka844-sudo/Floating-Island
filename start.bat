@echo off
cd /d "%~dp0"
set "PYW=C:\Users\Szymon\AppData\Local\Python\pythoncore-3.15-64\pythonw.exe"
if not exist "%PYW%" set "PYW=C:\Users\Szymon\AppData\Local\Python\bin\pythonw.exe"
if not exist "%PYW%" set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
start "" "%PYW%" "%~dp0main.py"
