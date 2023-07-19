tasklist | find "exportana_runner.exe" > nul
if %errorlevel% GTR 0 (start C:\Source\Exportana\exportana_runner.exe)
exit 0