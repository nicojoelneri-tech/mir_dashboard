@echo off
title Mock NVR — Mir Soluciones
cd /d "C:\Users\nicol\OneDrive\Documentos\Proyecto Mir\scripts"
echo Iniciando servidores mock NVR...
echo Puerto 8765 = Hikvision DS-7608NI
echo Puerto 8766 = Dahua XVR5108H
echo Puerto 8767 = Intelbras MHDX 3008
echo.
"C:\Users\nicol\AppData\Local\Programs\Python\Python312\python.exe" mir_mock_nvr.py
pause
