# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contexto del proyecto

**Mir Soluciones** — plataforma de monitoreo de red para clientes (SaaS). El agente Python corre en la máquina del cliente, mide conectividad y dispositivos en la red local, y sube los datos a Firebase. El dashboard web muestra esa información en tiempo real.

## Arquitectura

```
Cliente (agente Python)
  └── mir_agente_test.py
        ├── ping → gateway, 8.8.8.8, 1.1.1.1
        ├── speedtest (cada 10 min, cacheado en mir_ultima_velocidad.json)
        ├── ARP scan (cada 5 min) → detecta dispositivos nuevos en la red
        └── sube reporte a Firebase Realtime DB cada 60 seg

Firebase Realtime Database (mir-soluciones-35859)
  └── /clientes/{cliente_id}/ultimo_reporte  ← PUT por el agente

Firebase Hosting → public/
  ├── index.html   (dashboard principal por cliente)
  └── mir-admin.html (panel de administración)
```

## Stack

- **Agente:** Python 3.x — sin frameworks, solo stdlib + `google-auth` + `speedtest-cli`
- **Backend:** Firebase Realtime Database (auth via service account JSON)
- **Frontend:** HTML/CSS/JS vanilla — sin bundlers, sin frameworks
- **Hosting:** Firebase Hosting (`firebase deploy --only hosting`)

## Comandos

```bash
# Correr el agente localmente (requiere mir-clave.json y dependencias)
python mir_agente_test.py

# Deploy del dashboard a Firebase Hosting
firebase deploy --only hosting

# Setup inicial (instala Node, Firebase CLI, hace login y deploy)
mir_hosting_setup.bat   # solo Windows
```

## Dependencias del agente Python

```
google-auth
google-auth-httplib2
speedtest-cli
```

El agente las instala automáticamente si faltan (auto-pip dentro del script).

## Archivos clave

| Archivo | Rol |
|---|---|
| `mir_agente_test.py` | Agente principal — loop de monitoreo |
| `mir-clave.json` | Service account de Firebase (**nunca commitear**) |
| `mir_ultima_velocidad.json` | Cache local del último speedtest |
| `mir_dispositivos_conocidos.json` | Historial de MACs detectadas (persiste entre reinicios) |
| `public/index.html` | Dashboard del cliente (lee Firebase en tiempo real) |
| `public/mir-admin.html` | Panel de administración |
| `firebase.json` | Config de Firebase Hosting (public dir, rewrites) |
| `.firebaserc` | Proyecto Firebase: `mir-soluciones-35859` |

## Configuración del agente

En `mir_agente_test.py`, las constantes al inicio:

```python
CLIENTE_ID        = "clientedemo"   # ID único por cliente
FIREBASE_URL      = "https://mir-soluciones-35859-default-rtdb.firebaseio.com"
CLAVE_JSON        = r"C:\...\mir-clave.json"
INTERVALO_SEG     = 60    # frecuencia de reporte
INTERVALO_ESCANEO = 300   # frecuencia de scan ARP
```

## Estructura del reporte Firebase

```json
{
  "cliente_id": "...",
  "ts": "2025-...",
  "red": {
    "gateway_ip": "192.168.1.1",
    "gateway_online": true,
    "gateway_latencia": 1.0,
    "internet_online": true,
    "internet_latencia": 12.0,
    "bajada_mbps": 95.3,
    "subida_mbps": 20.1,
    "estado": "CONEXION NORMAL",
    "dispositivos_red": [...],
    "total_dispositivos": 5
  },
  "alertas": [
    {"tipo": "internet_offline", "ts": "..."},
    {"tipo": "dispositivo_nuevo", "ip": "...", "mac": "...", "fabricante": "..."}
  ],
  "agente_version": "2.0"
}
```

## Reglas importantes

- `mir-clave.json` contiene credenciales privadas — **nunca commitear ni exponer**
- El agente guarda offline en `mir_offline_<timestamp>.json` si Firebase falla
- El escaneo ARP no requiere privilegios de admin; usa `arp -a` y ping sweep (20 hosts por defecto)
- El dashboard HTML lee Firebase directamente desde el browser con JS (sin backend propio)

## Tareas pendientes

1. 🔲 **Monitoreo de electricidad** — Agregar soporte para sensor de voltaje/tensión en el agente. Mostrar voltaje actual en dashboard del cliente y detectar bajadas de tensión, alertar cuando cae por debajo de umbral.
2. 🔲 **Instalador/paquete final** — Reemplazar la instalación manual por un paquete intuitivo para el técnico instalador: creación de usuario, configuración de DVR/NVR, credenciales, todo en un flujo guiado (wizard).
3. 🔲 **Gestión de usuarios en admin** — Mauro debe poder ver usuarios de clientes en el panel admin (sin ver claves), con opción de blanquear/resetear contraseña cuando el cliente lo requiera.
