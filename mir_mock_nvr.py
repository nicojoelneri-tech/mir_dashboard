"""
Mir Soluciones — Servidor mock para testear integración de cámaras
==================================================================
Simula las respuestas de un NVR Hikvision y un DVR Dahua.
No requiere hardware real. Acepta cualquier credencial.

Uso:
  1. Correr este script: python mir_mock_nvr.py
  2. Copiar el mir_camaras.json que imprime en pantalla
  3. Correr el agente normalmente: python mir_agente_test.py
  4. Ver los datos en el dashboard de Firebase

Ctrl+C para detener.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT_HIK = 8765
PORT_DAH = 8766

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
#  HANDLERS HTTP
# ══════════════════════════════════════════════

class HikvisionHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if   "/ISAPI/System/deviceInfo"        in self.path: self._xml(HIK_DEVICE_INFO)
        elif "/ISAPI/ContentMgmt/Storage"      in self.path: self._xml(HIK_STORAGE)
        elif "/ISAPI/Streaming/channels"        in self.path: self._xml(HIK_CHANNELS)
        elif "/ISAPI/ContentMgmt/record/tracks" in self.path: self._xml(HIK_TRACKS)
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
        if   "magicBox.cgi"      in self.path: self._txt(DAHUA_SYSINFO)
        elif "storageManager.cgi" in self.path: self._txt(DAHUA_STORAGE)
        elif "recordManager.cgi"  in self.path: self._txt(DAHUA_RECORD_STATUS)
        elif "configManager.cgi"  in self.path: self._txt(DAHUA_CHANNEL_TITLES)
        else:
            self.send_response(404); self.end_headers()

    def _txt(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=UTF-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"  [DAH] {self.path.split('?')[0]}")


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    srv_hik = HTTPServer(("127.0.0.1", PORT_HIK), HikvisionHandler)
    srv_dah = HTTPServer(("127.0.0.1", PORT_DAH), DahuaHandler)

    threading.Thread(target=srv_dah.serve_forever, daemon=True).start()

    config_test = json.dumps([
        {
            "nombre": "NVR Test (Hikvision DS-7608NI)",
            "marca":  "hikvision",
            "ip":     "127.0.0.1",
            "usuario": "admin",
            "password": "test",
            "puerto": PORT_HIK
        },
        {
            "nombre": "DVR Test (Dahua XVR5108H)",
            "marca":  "dahua",
            "ip":     "127.0.0.1",
            "usuario": "admin",
            "password": "test",
            "puerto": PORT_DAH
        }
    ], indent=2, ensure_ascii=False)

    sep = "  " + "═" * 50
    print()
    print(sep)
    print("  Mir Mock NVR — Servidor de prueba activo")
    print(sep)
    print()
    print(f"  Hikvision NVR  →  http://127.0.0.1:{PORT_HIK}")
    print(f"  Dahua DVR      →  http://127.0.0.1:{PORT_DAH}")
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
        srv_hik.serve_forever()
    except KeyboardInterrupt:
        print("\n  Mock detenido.")
