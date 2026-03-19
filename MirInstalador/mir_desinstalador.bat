@echo off
setlocal enabledelayedexpansion
title Mir Soluciones - Desinstalador

echo.
echo  ===================================================
echo   M.I.R. Soluciones - Desinstalador de agente
echo  ===================================================
echo.
echo  Este proceso va a:
echo    1. Detener el agente si esta corriendo
echo    2. Eliminar la tarea de inicio automatico
echo    3. Eliminar los archivos de instalacion
echo.

set /p CONFIRMAR= Confirmar desinstalacion? (S/N):
if /i "!CONFIRMAR!" neq "S" (
    echo  Desinstalacion cancelada.
    pause
    exit /b 0
)

echo.

:: 1. Terminar proceso del agente
echo  [..] Deteniendo agente...
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe /fi "WINDOWTITLE eq Mir*" >nul 2>&1
echo  [OK] Proceso detenido.

:: 2. Eliminar tareas programadas MirAgente_*
echo  [..] Eliminando tareas de inicio automatico...
set TAREAS_ELIMINADAS=0
for /f "tokens=*" %%t in ('schtasks /query /fo list 2^>nul ^| findstr /i "MirAgente"') do (
    set LINEA=%%t
    set NOMBRE=!LINEA:Nombre de tarea:=!
    set NOMBRE=!NOMBRE: =!
    if not "!NOMBRE!"=="" (
        schtasks /delete /tn "!NOMBRE!" /f >nul 2>&1
        set /a TAREAS_ELIMINADAS+=1
    )
)
:: Fallback: intentar borrar por patron comun
schtasks /delete /tn "MirAgente_*" /f >nul 2>&1
echo  [OK] Tareas eliminadas.

:: 3. Eliminar VBS de carpeta Inicio (fallback de autostart)
echo  [..] Limpiando carpeta Inicio de Windows...
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MirAgente_*.vbs" >nul 2>&1
echo  [OK] Carpeta Inicio limpia.

:: 4. Eliminar archivos de la carpeta de instalacion
echo  [..] Eliminando archivos de instalacion...
set DIR=%~dp0
cd /d "%TEMP%"
del /f /q "!DIR!mir_agente_test.py" >nul 2>&1
del /f /q "!DIR!mir_config.json" >nul 2>&1
del /f /q "!DIR!mir_camaras.json" >nul 2>&1
del /f /q "!DIR!mir_ultima_velocidad.json" >nul 2>&1
del /f /q "!DIR!mir_dispositivos_conocidos.json" >nul 2>&1
del /f /q "!DIR!mir_inicio.bat" >nul 2>&1
del /f /q "!DIR!mir_offline_*.json" >nul 2>&1
echo  [OK] Archivos eliminados.

echo.
echo  ===================================================
echo   Desinstalacion completada.
echo   Podés eliminar esta carpeta manualmente:
echo   !DIR!
echo  ===================================================
echo.
pause
