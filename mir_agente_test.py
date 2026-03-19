"""
Mir Soluciones — Agente de prueba con Firebase + escaneo de red
===============================================================
Monitorea tu conexion a internet, sube los datos a Firebase
y escanea dispositivos en la red local.
Ejecutar: python mir_agente_test.py
Detener:  Ctrl + C
"""

import subprocess
import platform
import datetime
import time
import json
import os
import re
import socket
import struct
import sys
import glob
import xml.etree.ElementTree as ET

# ─────────────────────────────────────────────
#  CONFIG  (defaults — se sobreescriben con mir_config.json)
# ─────────────────────────────────────────────
CLIENTE_ID   = "clientedemo"
FIREBASE_URL = "https://mir-soluciones-35859-default-rtdb.firebaseio.com"
CLAVE_JSON   = r"mir-clave.json"

INTERVALO_SEG       = 60   # intervalo general
INTERVALO_ESCANEO   = 300  # escanear red cada 5 minutos

# Directorio base del agente (funciona aunque lo inicie el Programador de tareas)
_DIR      = os.path.dirname(os.path.abspath(__file__))
_cfg_path = os.path.join(_DIR, "mir_config.json")
if os.path.exists(_cfg_path):
    try:
        with open(_cfg_path, encoding="utf-8") as _f:
            _cfg = json.load(_f)
        CLIENTE_ID        = _cfg.get("cliente_id",        CLIENTE_ID)
        FIREBASE_URL      = _cfg.get("firebase_url",      FIREBASE_URL)
        CLAVE_JSON        = _cfg.get("clave_json",         CLAVE_JSON)
        INTERVALO_SEG     = _cfg.get("intervalo_seg",     INTERVALO_SEG)
        INTERVALO_ESCANEO = _cfg.get("intervalo_escaneo", INTERVALO_ESCANEO)
    except Exception as _e:
        print(f"  [!] Error leyendo mir_config.json: {_e}")

# Suprimir ventanas CMD cuando el agente corre en segundo plano con pythonw
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0

# Cache local para no repetir consultas
_vendor_cache = {}

def obtener_fabricante(mac):
    if not mac:
        return "Desconocido"
    prefijo = mac[:8].upper()
    if prefijo in _vendor_cache:
        return _vendor_cache[prefijo]
    try:
        import urllib.request
        url = f"https://api.macvendors.com/{mac[:8]}"
        req = urllib.request.Request(url, headers={"User-Agent": "MirAgente/2.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            vendor = resp.read().decode("utf-8").strip()
            _vendor_cache[prefijo] = vendor
            return vendor
    except Exception:
        _vendor_cache[prefijo] = "Desconocido"
        return "Desconocido"

# ─────────────────────────────────────────────
#  DETECCIÓN DE ISP
# ─────────────────────────────────────────────

_isp_cache = {}

def detectar_isp():
    """Detecta el proveedor de internet usando ip-api.com (cache 1 hora)."""
    global _isp_cache
    if _isp_cache.get("ts") and time.time() - _isp_cache["ts"] < 3600:
        return _isp_cache
    archivo_cache = os.path.join(_DIR, "mir_isp_cache.json")
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://ip-api.com/json?fields=isp,org,as,query",
            headers={"User-Agent": "MirAgente/2.1"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        _isp_cache = {
            "ts":         time.time(),
            "isp":        data.get("isp", ""),
            "org":        data.get("org", ""),
            "asn":        data.get("as", ""),
            "ip_publica": data.get("query", "")
        }
        with open(archivo_cache, "w") as f:
            json.dump(_isp_cache, f)
        return _isp_cache
    except Exception:
        # Fallback: intentar leer caché del disco
        if os.path.exists(archivo_cache):
            try:
                with open(archivo_cache) as f:
                    _isp_cache = json.load(f)
                return _isp_cache
            except Exception:
                pass
        return {}

# ─────────────────────────────────────────────
#  FIREBASE
# ─────────────────────────────────────────────
firebase_token        = None
firebase_token_expira = 0

def obtener_token():
    global firebase_token, firebase_token_expira
    if firebase_token and time.time() < firebase_token_expira - 60:
        return firebase_token
    try:
        import google.oauth2.service_account as sa
        import google.auth.transport.requests as ga
        creds = sa.Credentials.from_service_account_file(
            CLAVE_JSON,
            scopes=["https://www.googleapis.com/auth/firebase",
                    "https://www.googleapis.com/auth/userinfo.email"]
        )
        creds.refresh(ga.Request())
        firebase_token        = creds.token
        firebase_token_expira = creds.expiry.timestamp()
        return firebase_token
    except Exception as e:
        print(f"  [!] Token error: {e}")
        return None

def enviar_firebase(datos, nodo="ultimo_reporte"):
    try:
        import urllib.request
        token = obtener_token()
        if not token:
            guardar_local(datos)
            return False
        url  = f"{FIREBASE_URL}/clientes/{CLIENTE_ID}/{nodo}.json"
        body = json.dumps(datos, default=str).encode("utf-8")
        req  = urllib.request.Request(
            url, data=body, method="PUT",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  [!] Firebase error: {e}")
        guardar_local(datos)
        return False

def guardar_historial(reporte):
    """Guarda entrada compacta en /historial y poda entradas > 30 días."""
    try:
        import urllib.request
        token = obtener_token()
        if not token:
            return
        ts_key = str(int(time.time()))
        # Entrada compacta: solo métricas clave + resumen de cámaras
        red = reporte.get("red") or {}
        entrada = {
            "ts":              reporte.get("ts"),
            "internet_online": red.get("internet_online"),
            "internet_lat":    red.get("internet_latencia"),
            "bajada_mbps":     red.get("bajada_mbps"),
            "subida_mbps":     red.get("subida_mbps"),
            "estado":          red.get("estado"),
            "alertas":         reporte.get("alertas") or [],
        }
        if reporte.get("camaras"):
            entrada["camaras"] = [
                {"nombre": c["nombre"], "online": c["online"],
                 "grabando": c.get("canales_grabando"), "activos": c.get("canales_activos")}
                for c in reporte["camaras"]
            ]
        # Guardar entrada
        url_put = f"{FIREBASE_URL}/clientes/{CLIENTE_ID}/historial/{ts_key}.json"
        body = json.dumps(entrada, default=str).encode("utf-8")
        req = urllib.request.Request(url_put, data=body, method="PUT",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)

        # Podar entradas con más de 30 días
        limite = int(time.time()) - (30 * 86400)
        url_q = (f"{FIREBASE_URL}/clientes/{CLIENTE_ID}/historial.json"
                 f'?orderBy=%22%24key%22&endAt=%22{limite}%22')
        req_q = urllib.request.Request(url_q,
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req_q, timeout=10) as resp:
            viejas = json.loads(resp.read()) or {}
        if viejas:
            patch = {k: None for k in viejas}
            url_p = f"{FIREBASE_URL}/clientes/{CLIENTE_ID}/historial.json"
            req_p = urllib.request.Request(url_p,
                data=json.dumps(patch).encode("utf-8"), method="PATCH",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            urllib.request.urlopen(req_p, timeout=10)
            print(f"  [OK] Historial: entrada guardada, {len(viejas)} entrada(s) podada(s).")
        else:
            print(f"  [OK] Historial: entrada guardada.")
    except Exception as e:
        print(f"  [!] Error guardando historial: {e}")

def guardar_local(datos):
    try:
        nombre = os.path.join(_DIR, f"mir_offline_{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
        with open(nombre, "w") as f:
            json.dump(datos, f, indent=2, default=str)
        print(f"  [!] Guardado local: {nombre}")
    except Exception:
        pass

def reintentar_offline():
    """Reenvía archivos offline pendientes y elimina los que tienen más de 7 días."""
    try:
        archivos = sorted(glob.glob(os.path.join(_DIR, "mir_offline_*.json")))
        if not archivos:
            return
        print(f"  [..] {len(archivos)} archivo(s) offline pendiente(s). Intentando reenviar...")
        enviados, viejos = 0, 0
        limite = time.time() - 7 * 86400
        for archivo in archivos:
            try:
                if os.path.getmtime(archivo) < limite:
                    os.remove(archivo)
                    viejos += 1
                    continue
                with open(archivo) as f:
                    datos = json.load(f)
                if enviar_firebase(datos):
                    os.remove(archivo)
                    enviados += 1
            except Exception:
                pass
        partes = []
        if enviados: partes.append(f"{enviados} reenviado(s)")
        if viejos:   partes.append(f"{viejos} viejo(s) eliminado(s)")
        if partes:   print(f"  [OK] Offline: {', '.join(partes)}.")
    except Exception:
        pass

def limpiar_dispositivos_viejos():
    """Elimina del historial local dispositivos no vistos en más de 60 días."""
    global dispositivos_conocidos
    try:
        limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60)
        antes  = len(dispositivos_conocidos)
        nuevos = {}
        for mac, d in dispositivos_conocidos.items():
            try:
                ts_d = datetime.datetime.fromisoformat(d.get("ts", "2000-01-01T00:00:00"))
                if ts_d.tzinfo is None:
                    ts_d = ts_d.replace(tzinfo=datetime.timezone.utc)
                if ts_d >= limite:
                    nuevos[mac] = d
            except Exception:
                nuevos[mac] = d  # conservar si no se puede parsear
        dispositivos_conocidos = nuevos
        eliminados = antes - len(dispositivos_conocidos)
        if eliminados:
            with open(archivo_dispositivos, "w") as f:
                json.dump(dispositivos_conocidos, f, indent=2, default=str)
            print(f"  [OK] Dispositivos: {eliminados} entrada(s) vieja(s) eliminada(s).")
    except Exception:
        pass

def limpiar_alertas_firebase():
    """Poda entradas de admin_config/alertas_ignoradas con más de 30 días."""
    try:
        import urllib.request
        token = obtener_token()
        if not token:
            return
        url = f"{FIREBASE_URL}/admin_config/alertas_ignoradas.json"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            alertas = json.loads(resp.read()) or {}
        if not alertas:
            return
        limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        viejas = {}
        for k, v in alertas.items():
            try:
                ts_a = datetime.datetime.fromisoformat(v.get("ts", "2000-01-01"))
                if ts_a.tzinfo is None:
                    ts_a = ts_a.replace(tzinfo=datetime.timezone.utc)
                if ts_a < limite:
                    viejas[k] = None
            except Exception:
                pass
        if viejas:
            patch = json.dumps(viejas).encode("utf-8")
            req_p = urllib.request.Request(url, data=patch, method="PATCH",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            urllib.request.urlopen(req_p, timeout=10)
            print(f"  [OK] Firebase: {len(viejas)} alerta(s) ignorada(s) vieja(s) podada(s).")
    except Exception:
        pass

# ─────────────────────────────────────────────
#  MONITOREO DE RED
# ─────────────────────────────────────────────
def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

def separador():
    print("─" * 52)

def ping(host, intentos=3):
    param = "-n" if platform.system().lower() == "windows" else "-c"
    try:
        resultado = subprocess.run(
            ["ping", param, str(intentos), host],
            capture_output=True, timeout=8, creationflags=_NO_WINDOW
        )
        stdout   = resultado.stdout.decode(sys.getdefaultencoding(), errors="replace")
        online   = resultado.returncode == 0
        latencia = None
        for linea in stdout.splitlines():
            if "tiempo=" in linea.lower() or "time=" in linea.lower():
                for parte in linea.split():
                    if "tiempo=" in parte.lower() or "time=" in parte.lower():
                        try:
                            latencia = float(parte.split("=")[-1].replace("ms","").strip())
                        except Exception:
                            pass
        return online, latencia
    except Exception:
        return False, None

def detectar_gateway():
    try:
        if platform.system().lower() == "windows":
            cmd = ('powershell -NoProfile -Command "(Get-NetRoute -DestinationPrefix \'0.0.0.0/0\' | Sort-Object RouteMetric | Select-Object -First 1).NextHop"')
            out = subprocess.check_output(cmd, shell=True, text=True, timeout=5, creationflags=_NO_WINDOW).strip()
            if out and re.match(r"^\d+\.\d+\.\d+\.\d+$", out):
                return out
        else:
            out = subprocess.check_output(["ip", "route"], text=True)
            for linea in out.splitlines():
                if linea.startswith("default"):
                    return linea.split()[2]
    except Exception:
        pass
    return "192.168.1.1"

def medir_velocidad():
    try:
        import speedtest
        print("  Midiendo velocidad (~20 seg)...")
        st = speedtest.Speedtest(secure=True)
        st.get_best_server()
        return round(st.download()/1_000_000, 1), round(st.upload()/1_000_000, 1)
    except Exception:
        return None, None

def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def calcular_rango_red(ip_local, mascara="255.255.255.0"):
    """Devuelve el prefijo de red (ej: 192.168.1)"""
    partes = ip_local.split(".")
    return f"{partes[0]}.{partes[1]}.{partes[2]}"

def escanear_arp():
    """
    Obtiene la tabla ARP del sistema — lista de dispositivos
    que respondieron recientemente en la red local.
    No requiere librerías externas ni privilegios de admin.
    """
    dispositivos = []
    try:
        if platform.system().lower() == "windows":
            out = subprocess.check_output("arp -a", shell=True, timeout=10, creationflags=_NO_WINDOW)
            out = out.decode(sys.getdefaultencoding(), errors="replace")
            for linea in out.splitlines():
                linea = linea.strip()
                partes = linea.split()
                if len(partes) >= 2:
                    ip  = partes[0]
                    mac = partes[1] if len(partes) > 1 else ""
                    # Filtrar IPs válidas y MACs válidas
                    if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip) and re.match(r"^([0-9a-f]{2}[-:]){5}[0-9a-f]{2}$", mac, re.I):
                        # Excluir broadcast y multicast
                        if not ip.endswith(".255") and not mac.startswith("ff") and not mac.startswith("01"):
                            mac_fmt = mac.replace("-", ":").upper()
                            fabricante = obtener_fabricante(mac_fmt)
                            # Intentar resolver hostname
                            hostname = ""
                            try:
                                socket.setdefaulttimeout(1.0)
                                hostname = socket.gethostbyaddr(ip)[0]
                            except Exception:
                                pass
                            finally:
                                socket.setdefaulttimeout(None)
                            dispositivos.append({
                                "ip":         ip,
                                "mac":        mac_fmt,
                                "fabricante": fabricante,
                                "hostname":   hostname,
                                "ts":         datetime.datetime.now(datetime.timezone.utc).isoformat()
                            })
        else:
            out = subprocess.check_output(["arp", "-a"], timeout=10, text=True)
            for linea in out.splitlines():
                match = re.search(r"(\d+\.\d+\.\d+\.\d+).*?([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})", linea, re.I)
                if match:
                    ip, mac = match.group(1), match.group(2).upper()
                    if not ip.endswith(".255"):
                        fabricante = obtener_fabricante(mac)
                        hostname = ""
                        try:
                            socket.setdefaulttimeout(1.0)
                            hostname = socket.gethostbyaddr(ip)[0]
                        except Exception:
                            pass
                        finally:
                            socket.setdefaulttimeout(None)
                        dispositivos.append({
                            "ip": ip, "mac": mac,
                            "fabricante": fabricante,
                            "hostname": hostname,
                            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        })
    except Exception as e:
        print(f"  [!] Error ARP: {e}")
    return dispositivos

def ping_sweep(prefijo, rango=(1, 20)):
    """
    Hace ping a un rango de IPs para poblar la tabla ARP.
    Rápido: solo 20 hosts por defecto, en paralelo.
    """
    is_windows = platform.system().lower() == "windows"

    procs = []
    for i in range(rango[0], rango[1]+1):
        ip = f"{prefijo}.{i}"
        if is_windows:
            cmd = ["ping", "-n", "1", "-w", "200", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]
        p = subprocess.Popen(cmd, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        procs.append(p)

    for p in procs:
        try:
            p.wait(timeout=2)
        except Exception:
            p.kill()

# ─────────────────────────────────────────────
#  MONITOREO DE CÁMARAS — MULTI-MARCA
# ─────────────────────────────────────────────

def _asegurar_requests():
    """Instala requests si no está disponible. Devuelve (req, HTTPDigestAuth) o None."""
    try:
        import requests as req
        from requests.auth import HTTPDigestAuth
        return req, HTTPDigestAuth
    except ImportError:
        try:
            print("  [..] Instalando requests para monitoreo de cámaras...")
            subprocess.run([sys.executable, "-m", "pip", "install", "requests", "--quiet"], timeout=60)
            import requests as req
            from requests.auth import HTTPDigestAuth
            return req, HTTPDigestAuth
        except Exception as e:
            print(f"  [!] No se pudo instalar requests: {e}")
            return None, None

def _resultado_base(config):
    return {
        "nombre":           config.get("nombre", config.get("ip", "?")),
        "ip":               config.get("ip", ""),
        "marca":            config.get("marca", "hikvision"),
        "online":           False,
        "modelo":           "",
        "discos":           [],
        "grabando":         False,
        "canales":          [],
        "canales_activos":  0,
        "canales_grabando": 0,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

# ── HIKVISION (ISAPI / XML) ──────────────────

def _xml_parse(text):
    """Parse XML de Hikvision eliminando namespaces."""
    try:
        root = ET.fromstring(text.encode("utf-8"))
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]
        return root
    except Exception:
        return None

def consultar_hikvision(config, req, HTTPDigestAuth):
    """Consulta NVR/DVR Hikvision via ISAPI. Soporta formato NVR (IDs 101,201…) y DVR (IDs 1,2,3…)."""
    ip     = config["ip"]
    puerto = config.get("puerto", 80)
    base   = f"http://{ip}:{puerto}/ISAPI"
    res    = _resultado_base(config)

    try:
        auth = HTTPDigestAuth(config["usuario"], config["password"])

        # 1. Online + modelo
        r = req.get(f"{base}/System/deviceInfo", auth=auth, timeout=5)
        if r.status_code != 200:
            return res
        res["online"] = True
        root = _xml_parse(r.text)
        if root is not None:
            res["modelo"] = (root.findtext("model") or root.findtext("deviceName") or "").strip()

        # 2. Discos
        r = req.get(f"{base}/ContentMgmt/Storage", auth=auth, timeout=5)
        if r.status_code == 200:
            root = _xml_parse(r.text)
            if root is not None:
                for hdd in root.iter("hdd"):
                    cap  = hdd.findtext("capacity")
                    free = hdd.findtext("freeSpace")
                    stat = hdd.findtext("status") or "desconocido"
                    try:
                        cap_i     = int(cap) if cap else 0
                        free_i    = int(free) if free else 0
                        cap_gb    = round(cap_i / 1024, 1)
                        free_gb   = round(free_i / 1024, 1)
                        usado_pct = round((cap_i - free_i) / cap_i * 100) if cap_i > 0 else 0
                    except Exception:
                        cap_gb, free_gb, usado_pct = 0, 0, 0
                    res["discos"].append({
                        "id": hdd.findtext("id") or "?",
                        "capacidad_gb": cap_gb, "libre_gb": free_gb,
                        "usado_pct": usado_pct, "estado": stat.lower()
                    })

        # 3. Canales — auto-detecta formato NVR (101,201…) vs DVR antiguo (1,2,3…)
        r = req.get(f"{base}/Streaming/channels", auth=auth, timeout=5)
        if r.status_code == 200:
            root = _xml_parse(r.text)
            if root is not None:
                canales_raw = []
                for ch in root.iter("StreamingChannel"):
                    ch_id  = str(ch.findtext("id") or "")
                    nombre = (ch.findtext("channelName") or f"Canal {ch_id}").strip()
                    activa = (ch.findtext("enabled") or "").lower() == "true"
                    canales_raw.append({"id": ch_id, "nombre": nombre, "activa": activa, "grabando": False})

                # Auto-detectar formato: si max ID >= 100 → NVR/DVR nuevo (filtrar main streams)
                ids_num = [int(c["id"]) for c in canales_raw if c["id"].isdigit()]
                if ids_num and max(ids_num) >= 100:
                    res["canales"] = [c for c in canales_raw if c["id"].endswith("01")]
                else:
                    res["canales"] = canales_raw  # DVR antiguo: cada ID es un canal físico

        # 4. Estado de grabación
        r = req.get(f"{base}/ContentMgmt/record/tracks", auth=auth, timeout=5)
        if r.status_code == 200:
            root = _xml_parse(r.text)
            if root is not None:
                activos = set()
                for track in root.iter("Track"):
                    if (track.findtext("enable") or track.findtext("enabled") or "").lower() == "true":
                        activos.add(track.findtext("id") or "")
                res["grabando"] = len(activos) > 0
                for canal in res["canales"]:
                    canal["grabando"] = canal["id"] in activos or res["grabando"]
        else:
            res["grabando"] = any(c["activa"] for c in res["canales"])
            for canal in res["canales"]:
                canal["grabando"] = canal["activa"]

    except Exception as e:
        print(f"  [!] Hikvision {ip}: {e}")

    res["canales_activos"]  = sum(1 for c in res["canales"] if c.get("activa"))
    res["canales_grabando"] = sum(1 for c in res["canales"] if c.get("grabando"))
    return res

# ── DAHUA (CGI / clave=valor) ────────────────

def _dahua_parse(text):
    """Parse respuesta CGI de Dahua (formato clave=valor)."""
    result = {}
    for line in text.strip().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result

def _dahua_indexed(data, prefix):
    """Extrae lista de objetos indexados: prefix[0].campo → [{campo: valor}]"""
    items = {}
    pat = re.compile(rf"^{re.escape(prefix)}\[(\d+)\]\.(.+)$")
    for k, v in data.items():
        m = pat.match(k)
        if m:
            idx, campo = int(m.group(1)), m.group(2)
            items.setdefault(idx, {})[campo] = v
    return [items[i] for i in sorted(items)]

def consultar_dahua(config, req, HTTPDigestAuth):
    """Consulta NVR/DVR Dahua via CGI HTTP API."""
    ip     = config["ip"]
    puerto = config.get("puerto", 80)
    base   = f"http://{ip}:{puerto}/cgi-bin"
    res    = _resultado_base(config)

    try:
        auth = HTTPDigestAuth(config["usuario"], config["password"])

        # 1. Online + modelo
        r = req.get(f"{base}/magicBox.cgi?action=getSystemInfo", auth=auth, timeout=5)
        if r.status_code != 200:
            return res
        res["online"] = True
        info = _dahua_parse(r.text)
        res["modelo"] = info.get("deviceType", info.get("serialNo", "")).strip()

        # 2. Discos — intenta dos endpoints según firmware
        for endpoint in [
            f"{base}/storageManager.cgi?action=getDeviceAllInfo",
            f"{base}/storageManager.cgi?action=getHddInfo"
        ]:
            r = req.get(endpoint, auth=auth, timeout=5)
            if r.status_code == 200 and "=" in r.text:
                data = _dahua_parse(r.text)
                # Formato nuevo: table.HddInfo[0].Field
                hdds = _dahua_indexed(data, "table.HddInfo")
                # Formato antiguo: hdd[0].field
                if not hdds:
                    hdds = _dahua_indexed(data, "hdd")
                for idx, d in enumerate(hdds):
                    try:
                        cap  = int(d.get("Capacity", d.get("capacity", 0)))
                        used = int(d.get("UsedBytes", d.get("used", 0)))
                        free = cap - used
                        cap_gb    = round(cap / 1024, 1)
                        free_gb   = round(free / 1024, 1)
                        usado_pct = round(used / cap * 100) if cap > 0 else 0
                    except Exception:
                        cap_gb, free_gb, usado_pct = 0, 0, 0
                    res["discos"].append({
                        "id": str(idx + 1),
                        "capacidad_gb": cap_gb, "libre_gb": free_gb,
                        "usado_pct": usado_pct,
                        "estado": d.get("Status", d.get("status", "desconocido")).lower()
                    })
                if res["discos"]:
                    break

        # 3. Canales y estado de grabación
        r = req.get(f"{base}/recordManager.cgi?action=getRecordStatus", auth=auth, timeout=5)
        if r.status_code == 200 and "=" in r.text:
            data = _dahua_parse(r.text)
            # Formato: status[0]=Recording / status[0]=Idle
            for k, v in sorted(data.items()):
                m = re.match(r"^status\[(\d+)\]$", k)
                if m:
                    idx      = int(m.group(1))
                    grabando = v.strip().lower() in ("recording", "1", "true")
                    res["canales"].append({
                        "id": str(idx + 1), "nombre": f"Canal {idx + 1}",
                        "activa": True, "grabando": grabando
                    })

        # Fallback: obtener nombres de canales si no hay estado de grabación
        if not res["canales"]:
            r = req.get(f"{base}/configManager.cgi?action=getConfig&name=ChannelTitle", auth=auth, timeout=5)
            if r.status_code == 200 and "=" in r.text:
                data  = _dahua_parse(r.text)
                hdds2 = _dahua_indexed(data, "table.ChannelTitle")
                for idx, d in enumerate(hdds2):
                    nombre = list(d.values())[0] if d else f"Canal {idx+1}"
                    res["canales"].append({
                        "id": str(idx + 1), "nombre": nombre.strip() or f"Canal {idx+1}",
                        "activa": True, "grabando": True
                    })

        res["grabando"] = any(c["grabando"] for c in res["canales"])

    except Exception as e:
        print(f"  [!] Dahua {ip}: {e}")

    res["canales_activos"]  = sum(1 for c in res["canales"] if c.get("activa"))
    res["canales_grabando"] = sum(1 for c in res["canales"] if c.get("grabando"))
    return res

# ── DISPATCHER ───────────────────────────────

def consultar_nvr(config):
    """Consulta un NVR/DVR según su marca. Soporta: hikvision, dahua."""
    req, HTTPDigestAuth = _asegurar_requests()
    if req is None:
        return _resultado_base(config)

    marca = config.get("marca", "hikvision").lower()
    if marca == "dahua":
        return consultar_dahua(config, req, HTTPDigestAuth)
    else:
        return consultar_hikvision(config, req, HTTPDigestAuth)

def cargar_config_camaras():
    """Carga la configuración de NVRs/DVRs desde mir_camaras.json."""
    ruta = os.path.join(_DIR, "mir_camaras.json")
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta) as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            marcas = set(c.get("marca", "hikvision") for c in data)
            print(f"  [OK] Config cámaras: {len(data)} equipo(s) — marcas: {', '.join(marcas)}")
            return data
    except Exception as e:
        print(f"  [!] Error leyendo mir_camaras.json: {e}")
    return []

# ─────────────────────────────────────────────
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────
archivo_velocidad    = os.path.join(_DIR, "mir_ultima_velocidad.json")
archivo_dispositivos = os.path.join(_DIR, "mir_dispositivos_conocidos.json")
medicion             = 0
ultima_escaneo       = 0
ultima_historial     = 0
ultima_limpieza      = 0
INTERVALO_HISTORIAL  = 600    # guardar historial cada 10 min
INTERVALO_LIMPIEZA   = 86400  # limpieza diaria

# Cargar dispositivos conocidos
dispositivos_conocidos = {}
if os.path.exists(archivo_dispositivos):
    try:
        with open(archivo_dispositivos) as f:
            dispositivos_conocidos = json.load(f)
    except Exception:
        pass

print()
separador()
print("  Mir Soluciones — Agente v2.0 con escaneo de red")
print(f"  Cliente: {CLIENTE_ID}")
print("  Presiona Ctrl+C para detener")
separador()

if not os.path.exists(CLAVE_JSON):
    print(f"\n  [ERROR] No se encontro la clave en:\n  {CLAVE_JSON}")
    input("\n  Presiona Enter para salir...")
    exit(1)

try:
    import google.oauth2.service_account
except ImportError:
    print("\n  [..] Instalando google-auth...")
    subprocess.run([
        r"C:\Users\nicol\AppData\Local\Programs\Python\Python312\python.exe",
        "-m", "pip", "install", "google-auth", "--quiet"
    ])
    print("  [OK] Reiniciá el script.")
    input("\n  Presiona Enter para salir...")
    exit(0)

config_camaras = cargar_config_camaras()

print("\n  [OK] Iniciando monitoreo...\n")
reintentar_offline()

while True:
    medicion += 1
    ahora = time.time()
    print(f"\n[{ts()}]  Medicion #{medicion}")
    separador()

    # ── RED E INTERNET ──
    gw = detectar_gateway()
    gw_ok,   gw_lat   = ping(gw)
    inet_ok, inet_lat = ping("8.8.8.8")
    cf_ok,   cf_lat   = ping("1.1.1.1")

    estado_gw   = f"OK  ({gw_lat:.0f} ms)"   if gw_ok and gw_lat   else ("OK" if gw_ok   else "OFFLINE")
    estado_inet = f"OK  ({inet_lat:.0f} ms)"  if inet_ok and inet_lat else ("OK" if inet_ok else "OFFLINE")
    estado_cf   = f"OK  ({cf_lat:.0f} ms)"    if cf_ok and cf_lat   else ("OK" if cf_ok   else "OFFLINE")

    print(f"  Router/Gateway  {gw:<18}  {estado_gw}")
    print(f"  Internet        8.8.8.8            {estado_inet}")
    print(f"  Cloudflare      1.1.1.1            {estado_cf}")

    # ── VELOCIDAD ──
    # Archivo de lock para evitar que múltiples instancias corran speedtest en simultáneo
    bajada, subida = None, None
    archivo_lock = archivo_velocidad + ".lock"
    medir = True

    if os.path.exists(archivo_velocidad):
        try:
            with open(archivo_velocidad) as f:
                ultima = json.load(f)
            if ahora - ultima.get("ts", 0) < 600:
                bajada, subida = ultima.get("bajada"), ultima.get("subida")
                medir = False
        except Exception:
            pass

    if medir:
        # Si otro agente ya está corriendo el speedtest, esperar y reintentar
        lock_activo = os.path.exists(archivo_lock) and (ahora - os.path.getmtime(archivo_lock) < 120)
        if lock_activo:
            medir = False  # otro proceso ya lo está midiendo, saltear esta vez
        else:
            try:
                open(archivo_lock, "w").close()  # crear lock
                bajada, subida = medir_velocidad()
                if bajada is not None:
                    try:
                        with open(archivo_velocidad, "w") as f:
                            json.dump({"ts": ahora, "bajada": bajada, "subida": subida}, f)
                    except Exception:
                        pass
            finally:
                try:
                    os.remove(archivo_lock)
                except Exception:
                    pass

    separador()
    if bajada is not None:
        print(f"  Bajada    {bajada} Mbps  |  Subida  {subida} Mbps")

    # ── ESCANEO DE RED ──
    dispositivos_actuales = []
    nuevos_dispositivos   = []

    if ahora - ultima_escaneo >= INTERVALO_ESCANEO:
        print(f"  [..] Escaneando red local...")
        ip_local = obtener_ip_local()
        if ip_local:
            prefijo = calcular_rango_red(ip_local)
            ping_sweep(prefijo, (1, 30))
            time.sleep(1)
            dispositivos_actuales = escanear_arp()

            # Detectar dispositivos nuevos
            for d in dispositivos_actuales:
                mac = d["mac"]
                if mac not in dispositivos_conocidos:
                    nuevos_dispositivos.append(d)
                    dispositivos_conocidos[mac] = d

            # Guardar conocidos
            try:
                with open(archivo_dispositivos, "w") as f:
                    json.dump(dispositivos_conocidos, f, indent=2, default=str)
            except Exception:
                pass

            ultima_escaneo = ahora
            print(f"  [OK] {len(dispositivos_actuales)} dispositivos en la red" +
                  (f" · {len(nuevos_dispositivos)} nuevo(s)" if nuevos_dispositivos else ""))

            for d in dispositivos_actuales:
                nuevo = " ★ NUEVO" if d["mac"] in [n["mac"] for n in nuevos_dispositivos] else ""
                nombre = d["hostname"] or d["fabricante"]
                print(f"       {d['ip']:<16} {nombre:<20} {d['mac']}{nuevo}")
    else:
        secs_restantes = int(INTERVALO_ESCANEO - (ahora - ultima_escaneo))
        print(f"  Red local: próximo escaneo en {secs_restantes}s")

    # ── ISP ──
    isp_info = detectar_isp()

    # ── CÁMARAS / NVR ──
    camaras_reporte = []
    if config_camaras:
        print(f"  [..] Consultando {len(config_camaras)} NVR(s)...")
        for cam_cfg in config_camaras:
            estado_cam = consultar_nvr(cam_cfg)
            camaras_reporte.append(estado_cam)
            icono   = "✓" if estado_cam["online"] else "✗"
            canales = f"{estado_cam['canales_grabando']}/{estado_cam['canales_activos']} grabando"
            disco0  = estado_cam["discos"][0] if estado_cam["discos"] else None
            disco_s = f" · disco {disco0['usado_pct']}%" if disco0 else ""
            print(f"       {cam_cfg.get('nombre', cam_cfg['ip'])}: {icono}  {canales}{disco_s}")

    # ── ESTADO ──
    if not inet_ok:
        estado = "SIN INTERNET"
    elif not gw_ok:
        estado = "SIN ACCESO AL ROUTER"
    else:
        estado = "CONEXION NORMAL"

    separador()
    print(f"  ESTADO: {estado}")
    separador()

    # ── ARMAR REPORTE ──
    alertas = []
    if not inet_ok:
        alertas.append({"tipo": "internet_offline", "ts": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    for d in nuevos_dispositivos:
        alertas.append({
            "tipo":       "dispositivo_nuevo",
            "ip":         d["ip"],
            "mac":        d["mac"],
            "fabricante": d["fabricante"],
            "ts":         d["ts"]
        })
    ts_ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for cam in camaras_reporte:
        if not cam["online"]:
            alertas.append({"tipo": "nvr_offline", "nvr": cam["nombre"], "ip": cam["ip"], "ts": ts_ahora})
        for disco in cam.get("discos", []):
            if disco.get("usado_pct", 0) >= 90:
                alertas.append({"tipo": "disco_lleno", "nvr": cam["nombre"],
                                 "disco": disco["id"], "usado_pct": disco["usado_pct"], "ts": ts_ahora})

    reporte = {
        "cliente_id": CLIENTE_ID,
        "ts":         datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "red": {
            "gateway_ip":          gw,
            "gateway_online":      gw_ok,
            "gateway_latencia":    gw_lat,
            "internet_online":     inet_ok,
            "internet_latencia":   inet_lat,
            "cf_latencia":         cf_lat,
            "bajada_mbps":         bajada,
            "subida_mbps":         subida,
            "estado":              estado,
            "isp":                 isp_info.get("isp") or None,
            "ip_publica":          isp_info.get("ip_publica") or None,
            "dispositivos_red":    dispositivos_actuales if dispositivos_actuales else None,
            "total_dispositivos":  len(dispositivos_actuales) if dispositivos_actuales else None
        },
        "camaras": camaras_reporte if camaras_reporte else None,
        "alertas": alertas,
        "agente_version": "2.1"
    }

    print("  [..] Enviando a Firebase...", end=" ", flush=True)
    ok = enviar_firebase(reporte)
    print("OK ✓" if ok else "ERROR")

    # ── HISTORIAL (cada 10 minutos) ──
    if ok and ahora - ultima_historial >= INTERVALO_HISTORIAL:
        guardar_historial(reporte)
        ultima_historial = ahora

    # ── LIMPIEZA DIARIA ──
    if ahora - ultima_limpieza >= INTERVALO_LIMPIEZA:
        print("\n  [..] Ejecutando limpieza diaria...")
        limpiar_dispositivos_viejos()
        limpiar_alertas_firebase()
        reintentar_offline()
        ultima_limpieza = ahora
        print("  [OK] Limpieza diaria completada.")

    print(f"\n  Proxima medicion en {INTERVALO_SEG} segundos...")
    try:
        time.sleep(INTERVALO_SEG)
    except KeyboardInterrupt:
        print("\n\n  Agente detenido. Hasta luego.")
        break
