@echo off
title Mir Soluciones - Configuracion de Hosting
color 0A

echo.
echo  ================================================
echo   Mir Soluciones - Configuracion de Hosting v1.0
echo  ================================================
echo.

:: ─────────────────────────────────────────────
::  VERIFICAR NODE.JS
:: ─────────────────────────────────────────────
echo  [..] Verificando Node.js...
node --version >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%v in ('node --version') do set NODE_VER=%%v
    echo  [OK] Node.js encontrado: %NODE_VER%
    goto verificar_firebase
)

echo  [..] Node.js no encontrado. Descargando...
echo.

:: Detectar arquitectura
set ARCH=64
if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    if not defined PROCESSOR_ARCHITEW6432 set ARCH=32
)

if "%ARCH%"=="64" (
    set NODE_URL=https://nodejs.org/dist/v20.11.1/node-v20.11.1-x64.msi
) else (
    set NODE_URL=https://nodejs.org/dist/v20.11.1/node-v20.11.1-x86.msi
)

curl -L --progress-bar -o "%TEMP%\node_installer.msi" "%NODE_URL%"

if not exist "%TEMP%\node_installer.msi" (
    echo  [ERROR] No se pudo descargar Node.js.
    pause & exit /b 1
)

echo.
echo  [..] Instalando Node.js...
msiexec /i "%TEMP%\node_installer.msi" /quiet /norestart

echo  [OK] Node.js instalado. Actualizando PATH...
:: Refrescar PATH
set "PATH=%PATH%;C:\Program Files\nodejs"
timeout /t 3 /nobreak >nul

:: ─────────────────────────────────────────────
::  VERIFICAR / INSTALAR FIREBASE CLI
:: ─────────────────────────────────────────────
:verificar_firebase
echo.
echo  [..] Verificando Firebase CLI...
call firebase --version >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%v in ('firebase --version') do set FB_VER=%%v
    echo  [OK] Firebase CLI encontrado: %FB_VER%
    goto login_firebase
)

echo  [..] Instalando Firebase CLI...
call npm install -g firebase-tools --quiet

if %errorlevel% neq 0 (
    echo  [ERROR] No se pudo instalar Firebase CLI.
    echo  Intentá cerrar y volver a abrir esta ventana.
    pause & exit /b 1
)
echo  [OK] Firebase CLI instalado.

:: ─────────────────────────────────────────────
::  LOGIN EN FIREBASE
:: ─────────────────────────────────────────────
:login_firebase
echo.
echo  ================================================
echo   Ahora vas a iniciar sesion en Firebase.
echo   Se va a abrir el navegador automaticamente.
echo   Iniciá sesion con la cuenta de Mauro.
echo  ================================================
echo.
pause

call firebase login

if %errorlevel% neq 0 (
    echo  [ERROR] No se pudo iniciar sesion en Firebase.
    pause & exit /b 1
)

:: ─────────────────────────────────────────────
::  INICIALIZAR HOSTING EN LA CARPETA DEL PROYECTO
:: ─────────────────────────────────────────────
echo.
echo  ================================================
echo   Configurando Firebase Hosting...
echo   Carpeta del proyecto: %~dp0
echo  ================================================
echo.

cd /d "%~dp0"

:: Crear carpeta public si no existe y mover el dashboard
if not exist "public" mkdir public
if exist "mir_dashboard.html" (
    copy "mir_dashboard.html" "public\index.html" >nul
    echo  [OK] Dashboard copiado a public\index.html
)

:: Crear firebase.json si no existe
if not exist "firebase.json" (
    echo { > firebase.json
    echo   "hosting": { >> firebase.json
    echo     "public": "public", >> firebase.json
    echo     "ignore": ["firebase.json", "**/.*", "**/node_modules/**"] >> firebase.json
    echo   } >> firebase.json
    echo } >> firebase.json
    echo  [OK] firebase.json creado
)

:: Crear .firebaserc con el proyecto
if not exist ".firebaserc" (
    echo { > .firebaserc
    echo   "projects": { >> .firebaserc
    echo     "default": "mir-soluciones-35859" >> .firebaserc
    echo   } >> .firebaserc
    echo } >> .firebaserc
    echo  [OK] .firebaserc creado
)

:: ─────────────────────────────────────────────
::  DEPLOY
:: ─────────────────────────────────────────────
echo.
echo  [..] Publicando dashboard en Firebase Hosting...
echo.
call firebase deploy --only hosting

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] El deploy fallo. Revisa los mensajes arriba.
    pause & exit /b 1
)

echo.
echo  ================================================
echo   Dashboard publicado con exito!
echo   URL: https://mir-soluciones-35859.web.app
echo  ================================================
echo.
pause
