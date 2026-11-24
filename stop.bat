@echo off
rem Stops every running WebGodEye process.
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -match '-m godeye' }; $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; 'Stopped ' + @($p).Count + ' WebGodEye process(es).'"
