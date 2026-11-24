@echo off
rem (Re)starts WebGodEye: stops any running copy first, then starts it in the background
rem (no console window) and opens the dashboard. Use this after editing watch.toml too.
cd /d "%~dp0"
call "%~dp0stop.bat" >nul
ping -n 2 127.0.0.1 >nul
start "" pythonw -m godeye %*
