"""
Mir Soluciones — Servidor mock para testear integración de cámaras
==================================================================
Simula las respuestas de un NVR Hikvision, un DVR Dahua y un DVR Intelbras.
No requiere hardware real. Acepta cualquier credencial.

Uso:
  1. Correr este script: python mir_mock_nvr.py
  2. Copiar el mir_camaras.json que imprime en pantalla
  3. Correr el agente normalmente: python mir_agente.py
  4. Ver los datos en el dashboard de Firebase

Ctrl+C para detener.

Escenarios simulados:
  - Hikvision: NVR con 3 canales activos (uno deshabilitado), responde recordStatus real
  - Dahua:     DVR con 8 canales, 6 grabando, 2 en Idle
  - Intelbras: DVR con 4 canales, disco al 85%, 3 grabando
  - Error 401: puerto 8769 → simula credenciales incorrectas
  - Timeout:   puerto 8770 → simula NVR que no responde
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT_HIK = 8765
PORT_DAH = 8766
PORT_INT = 8767  # Intelbras (CGI idéntico a Dahua)
PORT_401 = 8769  # Simula 401 Unauthorized
PORT_TMO = 8770  # Simula timeout (no responde)

# ══════════════════════════════════════════════
#  RESPUESTAS HIKVISION (ISAPI / XML)
# ══════════════════════════════════════════════

HIK_DEVICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<DeviceInfo xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <deviceName>NVR Mock</deviceName>
  <model>DS-7608NI-K2</model>
  <serialNumber>TEST-HIK-001</serialNumber>
  <firmwareVersion>V4.30.085</firmwareVersion>
  <deviceType>NVR</deviceType>
</DeviceInfo>"""

HIK_STORAGE = """<?xml version="1.0" encoding="UTF-8"?>
<storage xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <hddList>
    <hdd>
      <id>1</id>
      <hddName>/dev/sda</hddName>
      <capacity>976762</capacity>
      <freeSpace>412540</freeSpace>
      <status>ok</status>
    </hdd>
  </hddList>
</storage>"""

HIK_CHANNELS = """<?xml version="1.0" encoding="UTF-8"?>
<StreamingChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <StreamingChannel>
    <id>101</id>
    <channelName>Entrada Principal</channelName>
    <enabled>true</enabled>
  </StreamingChannel>
  <StreamingChannel>
    <id>102</id>
    <channelName>Entrada Principal Sub</channelName>
    <enabled>true</enabled>
  </StreamingChannel>
  <StreamingChannel>
    <id>201</id>
    <channelName>Estacionamiento</channelName>
    <enabled>true</enabled>
  </StreamingChannel>
  <StreamingChannel>
    <id>202</id>
    <channelName>Estacionamiento Sub</channelName>
    <enabled>true</enabled>
  </StreamingChannel>
  <StreamingChannel>
    <id>301</id>
    <channelName>Depósito</channelName>
    <enabled>true</enabled>
  </StreamingChannel>
  <StreamingChannel>
    <id>401</id>
    <channelName>Oficina</channelName>
    <enabled>false</enabled>
  </StreamingChannel>
</StreamingChannelList>"""

HIK_TRACKS = """<?xml version="1.0" encoding="UTF-8"?>
<TrackList xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <Track>
    <id>101</id>
    <channelID>1</channelID>
    <enable>true</enable>
  </Track>
  <Track>
    <id>201</id>
    <enable>true</enable>
  </Track>
  <Track>
    <id>301</id>
    <enable>true</enable>
  </Track>
  <Track>
    <id>401</id>
    <enable>false</enable>
  </Track>
</TrackList>"""

# recordStatus: estado REAL de grabación (endpoint nuevo — el correcto)
HIK_RECORD_STATUS = """<?xml version="1.0" encoding="UTF-8"?>
<StreamStatusList xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <StreamStatus>
    <id>101</id>
    <recordStatus>recording</recordStatus>
  </StreamStatus>
  <StreamStatus>
    <id>201</id>
    <recordStatus>recording</recordStatus>
  </StreamStatus>
  <StreamStatus>
    <id>301</id>
    <recordStatus>idle</recordStatus>
  </StreamStatus>
  <StreamStatus>
    <id>401</id>
    <recordStatus>idle</recordStatus>
  </StreamStatus>
</StreamStatusList>"""

# ══════════════════════════════════════════════
#  RESPUESTAS DAHUA (CGI / clave=valor)
# ══════════════════════════════════════════════

DAHUA_SYSINFO = """serialNo=TEST-DAH-001
deviceType=XVR5108H-4KL
hardwareVersion=1.00
firmwareVersion=V4.001.0000000.2"""

DAHUA_STORAGE = """table.HddInfo[0].Name=/dev/sda
table.HddInfo[0].Status=Normal
table.HddInfo[0].Capacity=1907726
table.HddInfo[0].UsedBytes=1480000
table.HddInfo[1].Name=/dev/sdb
table.HddInfo[1].Status=Normal
table.HddInfo[1].Capacity=1907726
table.HddInfo[1].UsedBytes=310000"""

DAHUA_RECORD_STATUS = """status[0]=Recording
status[1]=Recording
status[2]=Idle
status[3]=Recording
status[4]=Recording
status[5]=Idle
status[6]=Recording
status[7]=Recording"""

DAHUA_CHANNEL_TITLES = """table.ChannelTitle[0]=Puerta Frontal
table.ChannelTitle[1]=Puerta Trasera
table.ChannelTitle[2]=Pasillo
table.ChannelTitle[3]=Caja
table.ChannelTitle[4]=Depósito
table.ChannelTitle[5]=Estacionamiento
table.ChannelTitle[6]=Escalera
table.ChannelTitle[7]=Recepción"""

# ══════════════════════════════════════════════
#  RESPUESTAS INTELBRAS (CGI idéntico a Dahua)
# ══════════════════════════════════════════════

INT_SYSINFO = """serialNo=TEST-INT-001
deviceType=MHDX 3008
hardwareVersion=1.00
firmwareVersion=V3.35.0000.2"""

INT_STORAGE = """table.HddInfo[0].Name=/dev/sda
table.HddInfo[0].Status=Normal
table.HddInfo[0].Capacity=1907726
table.HddInfo[0].UsedBytes=1620000"""

# Disco al 85% — debe aparecer como advertencia en el dashboard
INT_RECORD_STATUS = """status[0]=Recording
status[1]=Recording
status[2]=Idle
status[3]=Recording"""

INT_CHANNEL_TITLES = """table.ChannelTitle[0]=Entrada
table.ChannelTitle[1]=Fondo
table.ChannelTitle[2]=Caja
table.ChannelTitle[3]=Deposito"""

# ══════════════════════════════════════════════
#  HANDLERS HTTP
# ══════════════════════════════════════════════

class HikvisionHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if   "/ISAPI/System/deviceInfo"                       in self.path: self._xml(HIK_DEVICE_INFO)
        elif "/ISAPI/ContentMgmt/Storage"                     in self.path: self._xml(HIK_STORAGE)
        elif "/ISAPI/Streaming/channels"                      in self.path: self._xml(HIK_CHANNELS)
        elif "/ISAPI/System/Video/inputs/streams/recordStatus" in self.path: self._xml(HIK_RECORD_STATUS)
        elif "/ISAPI/ContentMgmt/record/tracks"               in self.path: self._xml(HIK_TRACKS)
        else:
            self.send_response(404); self.end_headers()

    def _xml(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=UTF-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"  [HIK] {self.path.split('?')[0]}")


class DahuaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if   "magicBox.cgi"       in self.path: self._txt(DAHUA_SYSINFO)
        elif "storageManager.cgi"  in self.path: self._txt(DAHUA_STORAGE)
        elif "recordManager.cgi"   in self.path: self._txt(DAHUA_RECORD_STATUS)
        elif "configManager.cgi"   in self.path: self._txt(DAHUA_CHANNEL_TITLES)
        else:
            self.send_response(404); self.end_headers()

    def _txt(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=UTF-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"  [DAH] {self.path.split('?')[0]}")


class IntelbrasHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if   "magicBox.cgi"       in self.path: self._txt(INT_SYSINFO)
        elif "storageManager.cgi"  in self.path: self._txt(INT_STORAGE)
        elif "recordManager.cgi"   in self.path: self._txt(INT_RECORD_STATUS)
        elif "configManager.cgi"   in self.path: self._txt(INT_CHANNEL_TITLES)
        else:
            self.send_response(404); self.end_headers()

    def _txt(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=UTF-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"  [INT] {self.path.split('?')[0]}")


class UnauthorizedHandler(BaseHTTPRequestHandler):
    """Simula credenciales incorrectas — responde 401 con Digest challenge válido."""
    def do_GET(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate",
            'Digest realm="Mock NVR", nonce="abc123def456", qop="auth", algorithm="MD5"')
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"  [401] {self.path.split('?')[0]}")


class TimeoutHandler(BaseHTTPRequestHandler):
    """Simula NVR que no responde — cuelga sin responder."""
    def do_GET(self):
        import time
        time.sleep(60)  # nunca responde dentro del timeout del agente

    def log_message(self, fmt, *args):
        print(f"  [TMO] {self.path.split('?')[0]} (colgado...)")


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    servers = [
        (PORT_HIK, HikvisionHandler,    "Hikvision DS-7608NI"),
        (PORT_DAH, DahuaHandler,        "Dahua XVR5108H"),
        (PORT_INT, IntelbrasHandler,    "Intelbras MHDX 3008"),
        (PORT_401, UnauthorizedHandler, "Error 401 (credenciales)"),
        (PORT_TMO, TimeoutHandler,      "Timeout (no responde)"),
    ]

    srv_main = None
    for port, handler, label in servers:
        srv = HTTPServer(("127.0.0.1", port), handler)
        if srv_main is None:
            srv_main = srv
        else:
            threading.Thread(target=srv.serve_forever, daemon=True).start()

    config_test = json.dumps([
        {"nombre": "NVR Hikvision DS-7608NI", "marca": "hikvision",
         "ip": "127.0.0.1", "usuario": "admin", "password": "test", "puerto": PORT_HIK},
        {"nombre": "DVR Dahua XVR5108H",      "marca": "dahua",
         "ip": "127.0.0.1", "usuario": "admin", "password": "test", "puerto": PORT_DAH},
        {"nombre": "DVR Intelbras MHDX 3008", "marca": "intelbras",
         "ip": "127.0.0.1", "usuario": "admin", "password": "test", "puerto": PORT_INT},
        {"nombre": "NVR Credenciales Malas",  "marca": "hikvision",
         "ip": "127.0.0.1", "usuario": "admin", "password": "wrong", "puerto": PORT_401},
        {"nombre": "NVR Sin Respuesta",       "marca": "dahua",
         "ip": "127.0.0.1", "usuario": "admin", "password": "test", "puerto": PORT_TMO},
    ], indent=2, ensure_ascii=False)

    sep = "  " + "═" * 55
    print()
    print(sep)
    print("  Mir Mock NVR — Servidores de prueba activos")
    print(sep)
    print()
    for port, _, label in servers:
        print(f"  {label:<30} →  http://127.0.0.1:{port}")
    print()
    print("  Reemplazá mir_camaras.json con esto:")
    print()
    for line in config_test.splitlines():
        print(f"    {line}")
    print()
    print("  Luego corré el agente normalmente.")
    print("  Ctrl+C para detener.")
    print()

    try:
        srv_main.serve_forever()
    except KeyboardInterrupt:
        print("\n  Mock detenido.")
