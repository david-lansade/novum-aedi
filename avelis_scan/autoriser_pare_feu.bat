@echo off
chcp 65001 > nul
REM A lancer avec un clic droit puis "Executer en tant qu administrateur"
netsh advfirewall firewall delete rule name="Avelis scan 8000" > /dev/null 2>&1
netsh advfirewall firewall add rule name="Avelis scan 8000" dir=in action=allow protocol=TCP localport=8000 profile=any
if errorlevel 1 (echo ECHEC : relancez ce fichier en tant qu administrateur.) else (echo Port 8000 ouvert pour le telephone.)
pause
