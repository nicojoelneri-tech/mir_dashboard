@echo off
:: mir_actualizador.bat — Aplica una actualización del agente Mir
:: Uso: mir_actualizador.bat <ruta_nuevo_script>
:: Llamado automáticamente por el agente al detectar una nueva versión.

set "NUEVO=%~1"
set "INSTALL_DIR=C:\Program Files\Mir Soluciones"
set "DEST=%INSTALL_DIR%\mir_agente.py"
set "BACKUP=%INSTALL_DIR%\mir_agente_backup.py"

if "%NUEVO%"=="" (
    echo [!] Uso: mir_actualizador.bat ^<ruta_nuevo_script^>
    exit /b 1
)

:: Esperar que el proceso anterior termine de cerrarse
timeout /t 4 /nobreak > nul

:: Guardar backup de la versión actual (por si hay que hacer rollback)
if exist "%DEST%" copy /Y "%DEST%" "%BACKUP%" > nul

:: Aplicar nueva versión
copy /Y "%NUEVO%" "%DEST%" > nul
if errorlevel 1 (
    echo [!] Error al copiar el archivo. Restaurando backup...
    copy /Y "%BACKUP%" "%DEST%" > nul
    exit /b 1
)

:: Limpiar archivo temporal
del "%NUEVO%" > nul 2>&1

:: Reiniciar el agente
set "NSSM=%INSTALL_DIR%\nssm.exe"
if exist "%NSSM%" (
    "%NSSM%" stop MirAgente > nul 2>&1
    timeout /t 2 /nobreak > nul
    "%NSSM%" start MirAgente > nul 2>&1
) else (
    taskkill /F /IM pythonw.exe > nul 2>&1
    timeout /t 2 /nobreak > nul
    start "" "%INSTALL_DIR%\mir_inicio.bat"
)

exit /b 0
