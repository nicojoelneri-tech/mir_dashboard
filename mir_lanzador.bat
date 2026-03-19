@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Mir Soluciones — Instalador

echo.
echo  ===================================================
echo   M.I.R. Soluciones — Instalador de agente
echo  ===================================================
echo.

:: ── Verificar si Python ya está instalado ─────────────────────────────────
python --version >nul 2>&1
if %errorlevel% == 0 (
    echo  [OK] Python encontrado.
    goto :instalar_paquetes
)

:: ── Python no encontrado — detectar sistema ───────────────────────────────
echo  [..] Python no encontrado. Detectando sistema operativo...

:: Detectar arquitectura (64 o 32 bit)
if exist "%ProgramFiles(x86)%" (
    set ARCH=amd64
) else (
    set ARCH=win32
)

:: Detectar version de Windows mediante WMI (mas confiable que ver)
for /f "tokens=2 delims==" %%v in (
    'wmic os get version /value 2^>nul ^| find "Version"'
) do set WIN_VER=%%v

:: Extraer major version (6 = Win7/8, 10 = Win10/11)
for /f "tokens=1 delims=." %%m in ("!WIN_VER!") do set WIN_MAJOR=%%m

echo  [i] Version de Windows: !WIN_VER! (major: !WIN_MAJOR!, arch: !ARCH!)

:: Windows 7/8 = major 6 → Python 3.8 (ultima version compatible)
:: Windows 10/11 = major 10 → Python 3.11
if "!WIN_MAJOR!" == "6" (
    set PY_VER=3.8.20
    set PY_FOLDER=Python38
) else (
    set PY_VER=3.11.9
    set PY_FOLDER=Python311
)

set PY_INSTALLER=python-%PY_VER%-%ARCH%.exe
set PY_URL=https://www.python.org/ftp/python/%PY_VER%/%PY_INSTALLER%
set PY_DEST=%TEMP%\%PY_INSTALLER%

echo  [..] Descargando Python %PY_VER% (%ARCH%)...
echo       Esto puede tardar unos minutos segun la velocidad de internet.
echo.

:: Intentar con curl (disponible en Win10+ nativo)
curl --version >nul 2>&1
if %errorlevel% == 0 (
    curl -L --progress-bar -o "%PY_DEST%" "%PY_URL%"
    goto :verificar_descarga
)

:: Fallback: PowerShell (Win7+)
powershell -Command "& { (New-Object Net.WebClient).DownloadFile('%PY_URL%', '%PY_DEST%') }" >nul 2>&1
if %errorlevel% == 0 goto :verificar_descarga

:: Ultimo fallback: certutil (Win7+, mas lento)
certutil -urlcache -split -f "%PY_URL%" "%PY_DEST%" >nul 2>&1

:verificar_descarga
if not exist "%PY_DEST%" (
    echo.
    echo  [ERROR] No se pudo descargar Python automaticamente.
    echo.
    echo  Descargalo manualmente desde:
    echo    https://www.python.org/downloads/
    echo.
    echo  Instala Python y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

:: ── Instalar Python silenciosamente ───────────────────────────────────────
echo  [..] Instalando Python %PY_VER%...
"%PY_DEST%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1

:: Actualizar PATH para esta sesion
set "PATH=%LOCALAPPDATA%\Programs\Python\%PY_FOLDER%;%LOCALAPPDATA%\Programs\Python\%PY_FOLDER%\Scripts;%PATH%"

:: Verificar que quedo instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] La instalacion de Python fallo o requiere reiniciar la terminal.
    echo  Cierra esta ventana, abri una nueva y vuelve a ejecutar mir_lanzador.bat
    pause
    exit /b 1
)
echo  [OK] Python %PY_VER% instalado correctamente.

:instalar_paquetes
:: ── Verificar tkinter (requerido para el instalador grafico) ──────────────
python -c "import tkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] tkinter no disponible en esta instalacion de Python.
    echo.
    echo  Solucion: desinstala Python y reinstalalo desde python.org
    echo  asegurandote de marcar la opcion "tcl/tk and IDLE".
    pause
    exit /b 1
)

:: ── Lanzar el instalador grafico ──────────────────────────────────────────
echo.
echo  [OK] Iniciando instalador grafico...
echo.
cd /d "%~dp0"
python mir_instalador_gui.py

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] El instalador cerro con error. Revisa los mensajes de arriba.
    pause
)
