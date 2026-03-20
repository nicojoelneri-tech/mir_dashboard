@echo off
setlocal enabledelayedexpansion
title Mir Soluciones - Instalador

:: Verificar privilegios de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [..] Solicitando permisos de administrador...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  ===================================================
echo   M.I.R. Soluciones - Instalador de agente
echo  ===================================================
echo.

:: Verificar si Python esta instalado (y no es el stub de Microsoft Store)
set PYTHON_OK=0
for /f "delims=" %%p in ('where python 2^>nul') do (
    echo %%p | findstr /i "WindowsApps" >nul
    if errorlevel 1 (
        set PYTHON_OK=1
    )
)

if "!PYTHON_OK!" == "1" (
    echo  [OK] Python encontrado.
    goto :instalar_gui
)

:: Python no encontrado - detectar sistema
echo  [..] Python no encontrado. Detectando sistema operativo...

:: Detectar arquitectura
if exist "%ProgramFiles(x86)%" (
    set ARCH=amd64
) else (
    set ARCH=win32
)

:: Detectar version de Windows
for /f "tokens=2 delims==" %%v in ('wmic os get version /value 2^>nul ^| find "Version"') do set WIN_VER=%%v
for /f "tokens=1 delims=." %%m in ("!WIN_VER!") do set WIN_MAJOR=%%m

echo  [i] Windows !WIN_VER! - Arquitectura: !ARCH!

:: Elegir version de Python segun Windows
if "!WIN_MAJOR!" == "6" (
    set PY_VER=3.8.20
    set PY_FOLDER=Python38
) else (
    set PY_VER=3.11.9
    set PY_FOLDER=Python311
)

set PY_INSTALLER=python-!PY_VER!-!ARCH!.exe
set PY_URL=https://www.python.org/ftp/python/!PY_VER!/!PY_INSTALLER!
set PY_DEST=%TEMP%\!PY_INSTALLER!

echo  [..] Descargando Python !PY_VER! (!ARCH!)...
echo       Esto puede tardar unos minutos.
echo.

:: Intentar con curl (Win10+ nativo)
curl --version >nul 2>&1
if !errorlevel! == 0 (
    curl -L --progress-bar -o "!PY_DEST!" "!PY_URL!"
    goto :verificar_descarga
)

:: Fallback: PowerShell
powershell -Command "(New-Object Net.WebClient).DownloadFile('!PY_URL!', '!PY_DEST!')" >nul 2>&1
if !errorlevel! == 0 goto :verificar_descarga

:: Ultimo fallback: certutil
certutil -urlcache -split -f "!PY_URL!" "!PY_DEST!" >nul 2>&1

:verificar_descarga
if not exist "!PY_DEST!" (
    echo.
    echo  [ERROR] No se pudo descargar Python automaticamente.
    echo  Descargalo manualmente desde: https://www.python.org/downloads/
    echo  Instala Python y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

:: Instalar Python silenciosamente
echo  [..] Instalando Python !PY_VER!...
"!PY_DEST!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1

:: Actualizar PATH para esta sesion
set "PATH=%LOCALAPPDATA%\Programs\Python\!PY_FOLDER!;%LOCALAPPDATA%\Programs\Python\!PY_FOLDER!\Scripts;%PATH%"

:: Verificar instalacion
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo  [ERROR] La instalacion fallo o requiere reiniciar la terminal.
    echo  Cierra esta ventana y vuelve a ejecutar mir_lanzador.bat
    pause
    exit /b 1
)
echo  [OK] Python !PY_VER! instalado correctamente.

:instalar_gui
:: Verificar tkinter
python -c "import tkinter" >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo  [ERROR] tkinter no disponible en esta instalacion de Python.
    echo  Desinstala Python y reinstalalo desde python.org
    echo  asegurandote de marcar la opcion tcl/tk and IDLE.
    pause
    exit /b 1
)

:: Lanzar instalador grafico
echo.
echo  [OK] Iniciando instalador grafico...
echo.
cd /d "%~dp0"
python mir_instalador_gui.py

if !errorlevel! neq 0 (
    echo.
    echo  [ERROR] El instalador cerro con error.
    pause
)
