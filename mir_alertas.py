#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mir Soluciones — Monitor de alertas
=====================================
Monitorea todos los clientes en Firebase y envía alertas por Telegram.
Diseñado para correr en Render.com (free tier) o cualquier servidor.

Variables de entorno requeridas:
  ADMIN_PASSWORD  — contraseña de admin@mirsoluciones.com
  PORT            — puerto HTTP (Render lo setea automáticamente)
"""

import json, os, sys, time, urllib.request, datetime, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Configuración ──────────────────────────────────────────────────────────────
FIREBASE_URL     = "https://mir-soluciones-35859-default-rtdb.firebaseio.com"
FIREBASE_API_KEY = "AIzaSyAiV60g7n6UdiHwXZ8S0dTbIBBk4bxdRZs"
ADMIN_EMAIL      = "admin@mirsoluciones.com"
ADMIN_PASSWORD   = os.environ.get("ADMIN_PASSWORD", "")
PORT             = int(os.environ.get("PORT", 10000))

INTERVALO_SEG    = 60
MINUTOS_OFFLINE  = 5
DISCO_PCT_ALERTA = 90

# ── Estado en memoria ─────────────────────────────────────────────────────────
_estado_clientes = {}
_firebase_token  = None
_token_expira    = 0
_tg_token        = None
_tg_chat_id      = None
_ultimo_ciclo    = None
_clientes_count  = 0

# ── Helpers ───────────────────────────────────────────────────────────────────
def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def http_post(url, body):
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data,
           headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

# ── Firebase ──────────────────────────────────────────────────────────────────
def obtener_token_firebase():
    global _firebase_token, _token_expira
    if _firebase_token and time.time() < _token_expira - 60:
        return _firebase_token
    try:
        data = http_post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
            {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "returnSecureToken": True}
        )
        if data.get("error"):
            raise Exception(data["error"].get("message", "Auth error"))
        _firebase_token = data["idToken"]
        _token_expira   = time.time() + int(data.get("expiresIn", 3600))
        log("Token Firebase renovado ✓")
        return _firebase_token
    except Exception as e:
        log(f"[!] Error auth Firebase: {e}")
        return None

def firebase_get(path):
    token = obtener_token_firebase()
    if not token:
        return None
    try:
        url = f"{FIREBASE_URL}/{path}.json?auth={token}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"[!] Error leyendo Firebase {path}: {e}")
        return None

def firebase_put(path, data):
    token = obtener_token_firebase()
    if not token:
        return False
    try:
        body = json.dumps(data).encode()
        req  = urllib.request.Request(
            f"{FIREBASE_URL}/{path}.json?auth={token}",
            data=body, method="PUT",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True
    except Exception as e:
        log(f"[!] Error escribiendo Firebase {path}: {e}")
        return False

# ── Persistencia de estado de alertas ─────────────────────────────────────────
ESTADO_PATH = "admin_config/alertas_estado"

def guardar_estado():
    firebase_put(ESTADO_PATH, _estado_clientes)

def cargar_estado():
    global _estado_clientes
    data = firebase_get(ESTADO_PATH)
    if isinstance(data, dict):
        _estado_clientes = data
        log(f"Estado de alertas restaurado ({len(data)} cliente(s)) ✓")
    else:
        log("Sin estado previo de alertas — empezando limpio.")

# ── Telegram ──────────────────────────────────────────────────────────────────
def telegram_send(mensaje):
    if not _tg_token or not _tg_chat_id:
        log(f"  [ALERTA sin Telegram] {mensaje}")
        return False
    try:
        http_post(
            f"https://api.telegram.org/bot{_tg_token}/sendMessage",
            {"chat_id": _tg_chat_id, "text": mensaje, "parse_mode": "HTML"}
        )
        log(f"  [TG] {mensaje[:80]}")
        return True
    except Exception as e:
        log(f"  [!] Error Telegram: {e}")
        return False

def cargar_config_telegram():
    global _tg_token, _tg_chat_id
    cfg = firebase_get("admin_config/telegram")
    if cfg and cfg.get("bot_token") and cfg.get("chat_id"):
        _tg_token   = cfg["bot_token"]
        _tg_chat_id = str(cfg["chat_id"])
        return True
    return False

# ── Detección ─────────────────────────────────────────────────────────────────
def parsear_ts(ts_str):
    if not ts_str:
        return None
    try:
        return datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return None

def minutos_desde(ts_dt):
    if not ts_dt:
        return 9999
    ahora = datetime.datetime.now(datetime.timezone.utc)
    if ts_dt.tzinfo is None:
        ts_dt = ts_dt.replace(tzinfo=datetime.timezone.utc)
    return (ahora - ts_dt).total_seconds() / 60

def revisar_clientes(clientes_data):
    global _estado_clientes, _clientes_count
    if not clientes_data:
        return
    _clientes_count = len(clientes_data)

    for cliente_id, datos in clientes_data.items():
        rep = (datos or {}).get("ultimo_reporte") or {}
        red = rep.get("red") or {}
        ts_rep = parsear_ts(rep.get("ts"))
        mins   = minutos_desde(ts_rep)

        online_ahora  = mins < MINUTOS_OFFLINE
        inet_ok_ahora = red.get("internet_online", True) if online_ahora else False

        estado_prev  = _estado_clientes.get(cliente_id, {})
        online_prev  = estado_prev.get("online")
        inet_prev    = estado_prev.get("inet_ok")
        nombre       = cliente_id.replace("_", " ").title()

        # Conectividad del agente
        if online_prev is None:
            pass  # primera vez — no alertar
        elif online_prev and not online_ahora:
            telegram_send(
                f"🔴 <b>{nombre}</b> — sin conexión\n"
                f"Sin reporte hace {mins:.0f} min."
            )
        elif not online_prev and online_ahora:
            telegram_send(f"🟢 <b>{nombre}</b> — conexión restaurada")
        elif online_ahora and inet_prev is not None:
            if inet_prev and not inet_ok_ahora:
                telegram_send(
                    f"🟡 <b>{nombre}</b> — sin internet\n"
                    f"El equipo está encendido pero sin acceso a internet."
                )
            elif not inet_prev and inet_ok_ahora:
                telegram_send(f"🟢 <b>{nombre}</b> — internet restaurado")

        # DVR / cámaras
        camaras     = rep.get("camaras") or []
        dvr_ok_ahora = all(c.get("online") for c in camaras) if camaras else True
        dvr_ok_prev  = estado_prev.get("dvr_ok", True)

        if online_ahora and camaras:
            if dvr_ok_prev and not dvr_ok_ahora:
                nvrs_off = [c["nombre"] for c in camaras if not c.get("online")]
                telegram_send(
                    f"📷 <b>{nombre}</b> — DVR/NVR offline\n"
                    f"Equipo(s): {', '.join(nvrs_off)}"
                )
            elif not dvr_ok_prev and dvr_ok_ahora:
                telegram_send(f"📷 <b>{nombre}</b> — DVR/NVR restaurado")

            # Disco lleno
            for cam in camaras:
                for disco in (cam.get("discos") or []):
                    pct   = disco.get("usado_pct", 0)
                    clave = f"disco_{cliente_id}_{cam['nombre']}_{disco['id']}"
                    if pct >= DISCO_PCT_ALERTA and not estado_prev.get(clave):
                        telegram_send(
                            f"💾 <b>{nombre}</b> — disco casi lleno\n"
                            f"DVR: {cam['nombre']} | Disco {disco['id']}: {pct}% usado"
                        )
                        _estado_clientes.setdefault(cliente_id, {})[clave] = True
                    elif pct < DISCO_PCT_ALERTA:
                        _estado_clientes.setdefault(cliente_id, {}).pop(clave, None)

        _estado_clientes[cliente_id] = {
            **_estado_clientes.get(cliente_id, {}),
            "online":  online_ahora,
            "inet_ok": inet_ok_ahora,
            "dvr_ok":  dvr_ok_ahora,
        }

# ── HTTP server (para que Render no mate el proceso) ─────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        status = {
            "status": "ok",
            "ultimo_ciclo": _ultimo_ciclo,
            "clientes_monitoreados": _clientes_count,
            "telegram_ok": bool(_tg_token and _tg_chat_id),
        }
        body = json.dumps(status).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silenciar logs HTTP

def iniciar_http():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log(f"HTTP health server en puerto {PORT}")
    server.serve_forever()

# ── Loop de monitoreo ─────────────────────────────────────────────────────────
def loop_monitoreo():
    global _ultimo_ciclo

    if not ADMIN_PASSWORD:
        log("[!] ADMIN_PASSWORD no configurada. Seteá la variable de entorno.")
        return

    log("Autenticando en Firebase...")
    token = obtener_token_firebase()
    if not token:
        log("[!] No se pudo autenticar. Verificá ADMIN_PASSWORD.")
        return
    log("Autenticado ✓")

    cargar_estado()

    if cargar_config_telegram():
        log(f"Telegram configurado — chat_id: {_tg_chat_id} ✓")
        telegram_send("🟢 <b>Mir Alertas iniciado</b>\nMonitoreando todos los clientes.")

        # Resumen de estado inicial
        clientes_iniciales = firebase_get("clientes")
        if clientes_iniciales:
            offline, sin_inet = [], []
            for cid, datos in clientes_iniciales.items():
                rep    = (datos or {}).get("ultimo_reporte") or {}
                red    = rep.get("red") or {}
                mins   = minutos_desde(parsear_ts(rep.get("ts")))
                nombre = cid.replace("_", " ").title()
                if mins >= MINUTOS_OFFLINE:
                    offline.append(f"• {nombre} (hace {mins:.0f} min)")
                elif not red.get("internet_online", True):
                    sin_inet.append(f"• {nombre}")
            if offline or sin_inet:
                msg = "📋 <b>Estado al iniciar:</b>"
                if offline:
                    msg += "\n\n🔴 Sin conexión:\n" + "\n".join(offline)
                if sin_inet:
                    msg += "\n\n🟡 Sin internet:\n" + "\n".join(sin_inet)
                telegram_send(msg)
            else:
                telegram_send("✅ Todos los clientes online al iniciar.")
    else:
        log("[!] Telegram no configurado en Firebase. Configuralo desde el admin panel.")

    ciclo = 0
    while True:
        try:
            ciclo += 1
            if ciclo % 10 == 0:
                cargar_config_telegram()

            clientes = firebase_get("clientes")
            if clientes:
                log(f"Revisando {len(clientes)} cliente(s)...")
                revisar_clientes(clientes)
            else:
                log("Sin datos de clientes.")

            _ultimo_ciclo = datetime.datetime.now().isoformat()
            guardar_estado()

        except Exception as e:
            log(f"[!] Error en ciclo: {e}")

        time.sleep(INTERVALO_SEG)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Mir Soluciones — Monitor de alertas")
    print("="*50 + "\n")

    # HTTP server en thread separado
    t_http = threading.Thread(target=iniciar_http, daemon=True)
    t_http.start()

    # Loop de monitoreo en el hilo principal
    loop_monitoreo()
