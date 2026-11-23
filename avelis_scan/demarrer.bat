@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Avelis - serveur de scan
py -3 serveur.py %*
if errorlevel 1 python serveur.py %*
pause
