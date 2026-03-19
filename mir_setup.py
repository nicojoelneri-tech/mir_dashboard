"""
Mir Soluciones — Asistente de configuración
============================================
Configura el agente de monitoreo para un nuevo cliente.
No requiere conocimientos técnicos.

Ejecutar: python mir_setup.py
"""

import os
import sys
import json
import re
import subprocess
import unicodedata

FIREBASE_URL  = "https://mir-soluciones-35859-default-rtdb.firebaseio.com"
DIR           = os.path.dirname(os.path.abspath(__file__))
AGENT_FILE    = os.path.join(DIR, "mir_agente_test.py")
CONFIG_FILE   = os.path.join(DIR, "mir_config.json")
CAMARAS_FILE  = os.path.join(DIR, "mir_camaras.json")

# ─────────────────────────────────────────────
#  HELPERS DE UI
# ─────────────────────────────────────────────

def sep(char="─"):
    print("  " + char * 52)

def titulo(texto):
    print()
    sep("═")
    print(f"  {texto}")
    sep("═")
    print()

def paso(n, total, texto):
    print()
    sep()
    print(f"  Paso {n} de {total}: {texto}")
    sep()
    print()

def pedir(prompt, default=None, opciones=None):
    sufijo = f" [{default}]" if default is not None else ""
    while True:
        try:
            valor = input(f"  {prompt}{sufijo}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Configuración cancelada.")
            sys.exit(0)
        if not valor and default is not None:
            return str(default)
        if not valor:
            print("  Campo requerido. Intentá de nuevo.")
            continue
        if opciones and valor.lower() not in [o.lower() for o in opciones]:
            print(f"  Opciones válidas: {', '.join(opciones)}")
            continue
        return valor

def pedir_si_no(prompt, default="s"):
    resp = pedir(f"{prompt} (s/n)", default=default).lower()
    return resp in ("s", "si", "sí", "y", "yes", "1")

def ok(texto):
    print(f"  [OK] {texto}")

def error(texto):
    print(f"  [!]  {texto}")

def info(texto):
    print(f"       {texto}")

# ─────────────────────────────────────────────
#  LÓGICA
# ─────────────────────────────────────────────

def slugify(nombre):
    """Convierte 'Ferretería López' → 'ferreteria_lopez'"""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s or "cliente"

def test_firebase(cliente_id, clave_json):
    try:
        import google.oauth2.service_account as sa
        import google.auth.transport.requests as ga
        import urllib.request
        creds = sa.Credentials.from_service_account_file(
            clave_json,
            scopes=["https://www.googleapis.com/auth/firebase.database",
                    "https://www.googleapis.com/auth/userinfo.email"]
        )
        creds.refresh(ga.Request())
        url = f"{FIREBASE_URL}/clientes/{cliente_id}.json"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {creds.token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200, ""
    except Exception as e:
        return False, str(e)

def test_camara(config):
    try:
        import requests
        from requests.auth import HTTPDigestAuth
        ip     = config["ip"]
        puerto = config.get("puerto", 80)
        auth   = HTTPDigestAuth(config["usuario"], config["password"])
        if config.get("marca", "hikvision") == "dahua":
            url = f"http://{ip}:{puerto}/cgi-bin/magicBox.cgi?action=getSystemInfo"
        else:
            url = f"http://{ip}:{puerto}/ISAPI/System/deviceInfo"
        r = requests.get(url, auth=auth, timeout=5)
        return r.status_code == 200, ""
    except Exception as e:
        return False, str(e)

def instalar_requests_si_falta():
    try:
        import requests  # noqa
    except ImportError:
        print("  [..] Instalando requests...", end=" ", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "requests", "--quiet"], timeout=60)
        print("OK")

def configurar_camaras():
    camaras = []
    while True:
        idx = len(camaras) + 1
        print(f"\n  ── Equipo #{idx} {'─' * 38}")
        nombre  = pedir("Nombre del equipo (ej: NVR Oficina)")
        print()
        print("  Marcas disponibles: hikvision, dahua")
        marca   = pedir("Marca", default="hikvision", opciones=["hikvision", "dahua"])
        ip      = pedir("IP del equipo (ej: 192.168.1.64)")
        usuario = pedir("Usuario", default="admin")
        pwd     = pedir("Contraseña")
        puerto  = pedir("Puerto HTTP", default="80")

        cfg = {
            "nombre":   nombre,
            "marca":    marca.lower(),
            "ip":       ip,
            "usuario":  usuario,
            "password": pwd,
            "puerto":   int(puerto)
        }

        print()
        print("  [..] Probando conexión...", end=" ", flush=True)
        ok_cam, err_cam = test_camara(cfg)
        if ok_cam:
            print("OK ✓")
            camaras.append(cfg)
        else:
            print(f"FALLO")
            error(f"No se pudo conectar: {err_cam}")
            info("Verificá IP, usuario y contraseña.")
            if pedir_si_no("¿Guardar igual y continuar?", default="n"):
                camaras.append(cfg)

        print()
        if not pedir_si_no("¿Agregar otro equipo de cámaras?", default="n"):
            break
    return camaras

def configurar_autostart(cliente_id):
    """
    Intenta configurar inicio automático con pythonw (sin ventana).
    Método 1: Programador de tareas (requiere permisos).
    Método 2: Carpeta Startup del usuario (no requiere permisos, siempre funciona).
    """
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    # Crear mir_inicio.bat en la carpeta del agente
    bat_path = os.path.join(DIR, "mir_inicio.bat")
    with open(bat_path, "w") as f:
        f.write(f'@echo off\r\ncd /d "{DIR}"\r\n"{pythonw}" "{AGENT_FILE}"\r\n')

    # Método 1: Programador de tareas
    try:
        task_name = f"MirAgente_{cliente_id}"
        result = subprocess.run([
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'"{bat_path}"',
            "/sc", "onlogon",
            "/f"
        ], capture_output=True, text=True)
        if result.returncode == 0:
            return True, "Programador de tareas"
    except Exception:
        pass

    # Método 2: Carpeta Startup del usuario (no requiere permisos de admin)
    try:
        startup_dir = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        # VBS wrapper: inicia el bat completamente sin ventana
        vbs_path = os.path.join(startup_dir, f"MirAgente_{cliente_id}.vbs")
        with open(vbs_path, "w") as f:
            f.write(
                f'Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.Run Chr(34) & "{bat_path}" & Chr(34), 0, False\r\n'
            )
        return True, "Carpeta Startup del usuario"
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────
#  FLUJO PRINCIPAL
# ─────────────────────────────────────────────

titulo("Mir Soluciones — Configuración inicial")
print("  Este asistente configura el agente de monitoreo")
print("  para un nuevo cliente. Tarda unos 5 minutos.")

# ── PASO 1: Cliente ──────────────────────────
paso(1, 4, "Datos del cliente")

nombre_cliente = pedir("Nombre del cliente (ej: Ferretería López)")
cliente_id_sug = slugify(nombre_cliente)
info(f"ID generado automáticamente: {cliente_id_sug}")
print()
cliente_id = pedir("Confirmar ID (o escribir otro)", default=cliente_id_sug)
cliente_id = re.sub(r"[^a-z0-9_]", "_", cliente_id.lower()).strip("_") or cliente_id_sug
ok(f"ID del cliente: {cliente_id}")

# ── PASO 2: Credenciales Firebase ────────────
paso(2, 4, "Credenciales de Firebase")
print("  Necesitás el archivo mir-clave.json.")
print(f"  Copialo en esta carpeta:")
print(f"  {DIR}")
print()

ruta_default = os.path.join(DIR, "mir-clave.json")
while True:
    ruta_clave = pedir("Ruta al archivo mir-clave.json", default=ruta_default)
    if os.path.exists(ruta_clave):
        ok("Archivo encontrado.")
        break
    error(f"No se encontró: {ruta_clave}")
    if not pedir_si_no("¿Intentar con otra ruta?", default="s"):
        error("Continuando sin verificar el archivo.")
        break

# ── PASO 3: Cámaras ─────────────────────────
paso(3, 4, "Cámaras / NVR (opcional)")
instalar_requests_si_falta()

tiene_camaras = pedir_si_no("¿El cliente tiene sistema de cámaras (NVR/DVR)?", default="n")
camaras = configurar_camaras() if tiene_camaras else []

if not tiene_camaras:
    ok("Sin cámaras configuradas. Se puede agregar después editando mir_camaras.json.")

# ── PASO 4: Verificación y guardado ─────────
paso(4, 4, "Verificación y guardado")

print("  [..] Verificando conexión a Firebase...", end=" ", flush=True)
ok_fb, err_fb = test_firebase(cliente_id, ruta_clave)
print("OK ✓" if ok_fb else f"FALLO — {err_fb}")
if not ok_fb:
    error("El agente no va a poder subir datos hasta que se resuelva.")
    info("Causas frecuentes: archivo mir-clave.json incorrecto o sin internet.")

# Guardar mir_config.json
config = {
    "cliente_id":        cliente_id,
    "firebase_url":      FIREBASE_URL,
    "clave_json":        ruta_clave,
    "intervalo_seg":     60,
    "intervalo_escaneo": 300
}
with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
ok(f"mir_config.json guardado.")

# Guardar mir_camaras.json
with open(CAMARAS_FILE, "w", encoding="utf-8") as f:
    json.dump(camaras, f, indent=2, ensure_ascii=False)
ok(f"mir_camaras.json guardado ({len(camaras)} equipo(s)).")

# Autostart
print()
if pedir_si_no("¿Iniciar el agente automáticamente al encender Windows?", default="s"):
    print("  [..] Configurando inicio automático...", end=" ", flush=True)
    ok_at, metodo = configurar_autostart(cliente_id)
    if ok_at:
        print("OK ✓")
        ok(f"Método: {metodo}")
    else:
        print("FALLO")
        error(metodo)
        info("Podés configurarlo manualmente desde el Programador de tareas de Windows.")

# ── Resumen ──────────────────────────────────
print()
sep("═")
print("  ¡Listo! Configuración completada.")
sep("═")
print()
print(f"  Cliente  : {nombre_cliente}")
print(f"  ID       : {cliente_id}")
print(f"  Firebase : {'OK' if ok_fb else 'verificar manualmente'}")
print(f"  Cámaras  : {len(camaras)} equipo(s) configurado(s)")
print()
print("  Para iniciar el agente ahora:")
print(f"  python mir_agente_test.py")
print()

if pedir_si_no("¿Iniciar el agente ahora mismo?", default="s"):
    print()
    ok("Iniciando agente...")
    print()
    subprocess.Popen([sys.executable, AGENT_FILE])
else:
    input("  Presioná Enter para salir...")
