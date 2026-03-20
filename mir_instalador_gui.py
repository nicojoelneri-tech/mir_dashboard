#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mir Soluciones — Instalador Gráfico v2.0
=========================================
Instala y configura el agente de monitoreo en la PC del cliente.
Compatible con Windows 7 / 8 / 10 / 11.

Ejecutar: python mir_instalador_gui.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os, sys, json, re, subprocess, threading, unicodedata, webbrowser

# ── Rutas ─────────────────────────────────────────────────────────────────────
FIREBASE_URL     = "https://mir-soluciones-35859-default-rtdb.firebaseio.com"
FIREBASE_API_KEY = "AIzaSyAiV60g7n6UdiHwXZ8S0dTbIBBk4bxdRZs"  # Web API key (público)
DASHBOARD_URL    = "https://mir-soluciones-35859.web.app"
AGENTE_EMAIL     = "agente@mir-soluciones.internal"
AGENTE_CONTRASENA= "4e7cee98cf"
DIR              = os.path.dirname(os.path.abspath(__file__))
AGENT_FILE       = os.path.join(DIR, "mir_agente.py")
CONFIG_FILE      = os.path.join(DIR, "mir_config.json")
CAMARAS_FILE     = os.path.join(DIR, "mir_camaras.json")
DESINT_FILE      = os.path.join(DIR, "mir_desinstalador.bat")
INSTALL_DIR      = r"C:\Program Files\Mir Soluciones"

# ── Paleta ────────────────────────────────────────────────────────────────────
C_HEADER  = "#1a2a4a"
C_GOLD    = "#d4a843"
C_BG      = "#f4f6f8"
C_WHITE   = "#ffffff"
C_TEXT    = "#1a1a2e"
C_GRAY    = "#6b7280"
C_VERDE   = "#16a34a"
C_ROJO    = "#dc2626"
C_BORDER  = "#d1d5db"
C_STEP_ON = "#d4a843"
C_STEP_OFF= "#9ca3af"
FNT       = "Segoe UI"

STEPS = ["Bienvenida", "Requisitos", "Cliente", "Cámaras", "Instalación", "Listo"]
LOGO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logo gris.png")

def _cargar_logo(master, max_w=220, max_h=88):
    """Carga mir_logo.png; retorna PhotoImage o None."""
    if not os.path.exists(LOGO_FILE):
        return None
    try:
        try:
            from PIL import Image, ImageTk
            img = Image.open(LOGO_FILE).convert("RGBA")
            img.thumbnail((max_w, max_h))
            return ImageTk.PhotoImage(img, master=master)
        except ImportError:
            raw = tk.PhotoImage(file=LOGO_FILE, master=master)
            factor = max(1, raw.width() // max_w, raw.height() // max_h)
            return raw.subsample(factor, factor) if factor > 1 else raw
    except Exception:
        return None

# ── Helpers de lógica ─────────────────────────────────────────────────────────
def slugify(nombre):
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "cliente"

def pkg_instalado(nombre):
    """Verifica si un paquete está instalado usando un subprocess separado
    (evita problemas con el import lock de Python en threads)."""
    modulo = nombre.replace("-", "_").split("[")[0]
    r = subprocess.run(
        [sys.executable, "-c", f"import {modulo}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=10
    )
    return r.returncode == 0

def instalar_pkg(nombre, log_cb):
    log_cb(f"  Instalando {nombre}...")
    pkgs = nombre.split()  # soporta "pkg-a pkg-b" como múltiples paquetes
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + pkgs + ["--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120
    )
    return r.returncode == 0

def test_firebase(cliente_id, email, contrasena):
    """Verifica credenciales Firebase del cliente usando email/password."""
    try:
        import urllib.request
        # Login con email/password
        url  = (f"https://identitytoolkit.googleapis.com/v1/"
                f"accounts:signInWithPassword?key={FIREBASE_API_KEY}")
        body = json.dumps({"email": email, "password": contrasena,
                           "returnSecureToken": True}).encode()
        req  = urllib.request.Request(url, data=body,
                    headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            token = json.loads(resp.read().decode())["idToken"]
        # Verificar acceso al nodo del cliente
        url2 = f"{FIREBASE_URL}/clientes/{cliente_id}.json?auth={token}"
        req2 = urllib.request.Request(url2)
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            return resp2.status in (200, 204), ""
    except Exception as e:
        return False, str(e)

def fetch_clientes(email, contrasena):
    """Obtiene la lista de clientes desde Firebase /usuarios/. Retorna (lista, error)."""
    try:
        import urllib.request
        url  = (f"https://identitytoolkit.googleapis.com/v1/"
                f"accounts:signInWithPassword?key={FIREBASE_API_KEY}")
        body = json.dumps({"email": email, "password": contrasena,
                           "returnSecureToken": True}).encode()
        req  = urllib.request.Request(url, data=body,
                    headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            token = json.loads(resp.read().decode())["idToken"]
        url2 = f"{FIREBASE_URL}/usuarios.json?auth={token}"
        with urllib.request.urlopen(url2, timeout=10) as resp2:
            data = json.loads(resp2.read().decode()) or {}
        clientes = []
        for uid, info in data.items():
            nombre     = info.get("nombre", "")
            cliente_id = info.get("cliente_id", "")
            if cliente_id:
                clientes.append({"nombre": nombre, "cliente_id": cliente_id})
        clientes.sort(key=lambda x: x["nombre"].lower())
        return clientes, ""
    except Exception as e:
        return [], str(e)

def test_camara(cfg):
    try:
        ip, puerto = cfg["ip"], cfg.get("puerto", 80)
        marca = cfg.get("marca", "hikvision").lower()
        if marca in ("dahua", "intelbras"):
            url = f"http://{ip}:{puerto}/cgi-bin/magicBox.cgi?action=getSystemInfo"
        else:
            url = f"http://{ip}:{puerto}/ISAPI/System/deviceInfo"
        try:
            import requests
            from requests.auth import HTTPDigestAuth
            r = requests.get(url, auth=HTTPDigestAuth(cfg["usuario"], cfg["password"]),
                             timeout=(3.05, 10))
            if r.status_code == 200:
                return True, ""
            elif r.status_code == 401:
                return False, "Credenciales incorrectas (401)"
            else:
                return False, f"Error HTTP {r.status_code}"
        except ImportError:
            import urllib.request, base64
            cred = base64.b64encode(f"{cfg['usuario']}:{cfg['password']}".encode()).decode()
            req = urllib.request.Request(url, headers={"Authorization": f"Basic {cred}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200, ""
    except Exception as e:
        return False, str(e)

def configurar_autostart(cliente_id, install_dir=None):
    if install_dir is None:
        install_dir = DIR
    agent_file = os.path.join(install_dir, "mir_agente.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    bat = os.path.join(install_dir, "mir_inicio.bat")
    vbs = os.path.join(install_dir, "mir_inicio.vbs")

    # Bat que lanza pythonw (sin ventana de consola)
    with open(bat, "w", encoding="utf-8") as f:
        f.write(f'@echo off\r\ncd /d "{install_dir}"\r\nset PYTHONIOENCODING=utf-8\r\n"{pythonw}" "{agent_file}"\r\n')

    # VBS que lanza el bat completamente invisible (sin ventana CMD)
    with open(vbs, "w", encoding="utf-8") as f:
        f.write(
            f'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.Run "cmd.exe /c ""{bat}""", 0, False\r\n'
        )

    # Intento 1: Programador de tareas via wscript (sin ventana)
    try:
        r = subprocess.run(
            ["schtasks", "/create", "/tn", f"MirAgente_{cliente_id}",
             "/tr", f'wscript.exe "{vbs}"', "/sc", "onlogon", "/rl", "limited", "/f"],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            return True, "Programador de tareas de Windows"
    except Exception:
        pass

    # Intento 2: VBS en carpeta Inicio (fallback)
    try:
        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        vbs_startup = os.path.join(startup, f"MirAgente_{cliente_id}.vbs")
        with open(vbs_startup, "w", encoding="utf-8") as f:
            f.write(
                f'Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.Run "cmd.exe /c ""{bat}""", 0, False\r\n'
            )
        return True, "Carpeta Inicio de Windows"
    except Exception as e:
        return False, str(e)

# ── Clase principal ───────────────────────────────────────────────────────────
class Instalador:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Instalador Mir Soluciones")
        self.root.geometry("640x580")
        self.root.resizable(False, False)
        self.root.configure(bg=C_BG)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self.current = 0
        self.camaras = []
        self._logo_img = _cargar_logo(self.root, max_w=160, max_h=64)

        # Variables de formulario
        self.v_id        = tk.StringVar()
        self.v_cam_nom   = tk.StringVar()
        self.v_cam_marca = tk.StringVar(value="hikvision")
        self.v_cam_ip    = tk.StringVar()
        self.v_cam_user  = tk.StringVar(value="admin")
        self.v_cam_pass  = tk.StringVar()
        self.v_cam_port  = tk.StringVar(value="80")
        self.v_tiene_cam = tk.BooleanVar(value=False)
        self.v_autostart = tk.BooleanVar(value=True)

        self._build_ui()
        self._show_page(0)

    # ── UI base ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=C_HEADER, height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.lbl_step_title = tk.Label(hdr, text="", font=(FNT, 13, "bold"),
                                        fg=C_WHITE, bg=C_HEADER)
        self.lbl_step_title.place(relx=0.5, rely=0.5, anchor="center")

        # Barra de pasos
        self.steps_bar = tk.Canvas(self.root, bg=C_WHITE, height=46, highlightthickness=0)
        self.steps_bar.pack(fill="x")

        # Separador
        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill="x")

        # Área de contenido con scroll vertical
        content_outer = tk.Frame(self.root, bg=C_BG)
        content_outer.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(content_outer, bg=C_BG, highlightthickness=0, bd=0)
        self._scrollbar = tk.Scrollbar(content_outer, orient="vertical",
                                        command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        # scrollbar se empaqueta solo cuando hace falta

        self.content = tk.Frame(self._canvas, bg=C_BG)
        self._cw = self._canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.content.bind("<Configure>", self._on_content_resize)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Separador inferior
        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill="x")

        # Botones
        btn_bar = tk.Frame(self.root, bg=C_WHITE, height=54)
        btn_bar.pack(fill="x")
        btn_bar.pack_propagate(False)

        self.btn_cancel = tk.Button(btn_bar, text="Cancelar", font=(FNT, 9),
            fg=C_GRAY, bg=C_WHITE, relief="flat", bd=0,
            cursor="hand2", command=self._cancelar)
        self.btn_cancel.place(x=16, y=14, width=80, height=28)

        self.btn_back = tk.Button(btn_bar, text="← Atrás", font=(FNT, 9),
            fg=C_TEXT, bg=C_WHITE, relief="flat", bd=0,
            cursor="hand2", command=self._back)
        self.btn_back.place(x=460, y=14, width=80, height=28)

        self.btn_next = tk.Button(btn_bar, text="Siguiente →", font=(FNT, 9, "bold"),
            fg=C_WHITE, bg=C_HEADER, relief="flat", bd=0,
            cursor="hand2", command=self._next, activebackground="#0f1f38",
            activeforeground=C_WHITE)
        self.btn_next.place(x=546, y=10, width=80, height=34)

    def _draw_steps(self):
        c = self.steps_bar
        c.delete("all")
        w = 640
        n = len(STEPS)
        slot = w // n
        for i, name in enumerate(STEPS):
            cx = slot * i + slot // 2
            done = i < self.current
            active = i == self.current
            color = C_STEP_ON if (done or active) else C_STEP_OFF
            r = 12 if active else 9
            c.create_oval(cx-r, 23-r, cx+r, 23+r,
                          fill=color, outline="")
            if done:
                c.create_text(cx, 23, text="✓", font=(FNT, 9, "bold"),
                              fill=C_WHITE)
            else:
                c.create_text(cx, 23, text=str(i+1), font=(FNT, 8, "bold"),
                              fill=C_WHITE if active else "#e5e7eb")
            c.create_text(cx, 41, text=name,
                          font=(FNT, 7), fill=color)
            if i < n - 1:
                lx = cx + r + 2
                rx = cx + slot - r - 2
                clr = C_STEP_ON if done else C_STEP_OFF
                c.create_line(lx, 23, rx, 23, fill=clr, width=2)

    def _show_page(self, idx):
        self.current = idx
        for w in self.content.winfo_children():
            w.destroy()
        self._canvas.yview_moveto(0)
        self._draw_steps()
        self.lbl_step_title.config(text=STEPS[idx])
        self.btn_back.config(state="normal" if idx > 0 else "disabled")
        self.btn_next.config(
            state="normal",
            text="Finalizar" if idx == len(STEPS)-1 else "Siguiente →"
        )
        pages = [self._pg_bienvenida, self._pg_requisitos, self._pg_cliente,
                 self._pg_camaras, self._pg_instalar, self._pg_listo]
        pages[idx]()

    def _next(self):
        if self.current == len(STEPS) - 1:
            self.root.destroy()
            return
        if not self._validar(self.current):
            return
        self._show_page(self.current + 1)

    def _back(self):
        if self.current > 0:
            self._show_page(self.current - 1)

    def _cancelar(self):
        if messagebox.askyesno("Cancelar", "¿Cancelar la instalación?"):
            self.root.destroy()

    # ── Scroll helpers ────────────────────────────────────────────────────────
    def _on_content_resize(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        # mostrar scrollbar solo si el contenido excede el área visible
        if self.content.winfo_reqheight() > self._canvas.winfo_height():
            self._scrollbar.pack(side="right", fill="y")
        else:
            self._scrollbar.pack_forget()

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._cw, width=event.width)

    def _on_mousewheel(self, event):
        if self.content.winfo_reqheight() > self._canvas.winfo_height():
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── Validaciones por página ───────────────────────────────────────────────
    def _validar(self, page):
        if page == 1:  # Requisitos
            if not self._req_ok:
                messagebox.showwarning("Verificación pendiente",
                    "Hacé click en 'Verificar e instalar' antes de continuar.")
                return False
        if page == 2:  # Cliente
            if not self.v_id.get().strip():
                messagebox.showwarning("Dato requerido", "Ingresá el ID del cliente.")
                return False
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # PÁGINAS
    # ══════════════════════════════════════════════════════════════════════════

    # ── Página 1: Bienvenida ──────────────────────────────────────────────────
    def _pg_bienvenida(self):
        f = tk.Frame(self.content, bg=C_BG)
        f.pack(expand=True)
        if self._logo_img:
            tk.Label(f, image=self._logo_img, bg=C_BG).pack(pady=(16, 6))
        else:
            tk.Label(f, text="M.I.R. Soluciones Integrales", font=(FNT, 22, "bold"),
                     fg=C_HEADER, bg=C_BG).pack(pady=(16, 6))
        tk.Label(f, text="Asistente de instalación del agente de monitoreo",
                 font=(FNT, 11), fg=C_GRAY, bg=C_BG).pack()
        tk.Frame(f, bg=C_GOLD, height=2, width=200).pack(pady=16)
        desc = ("Este asistente configurará el agente de monitoreo de red\n"
                "en este equipo. Solo necesitarás ingresar los datos del\n"
                "cliente y del sistema de cámaras.\n\n"
                "Tiempo estimado: 3 a 5 minutos.")
        tk.Label(f, text=desc, font=(FNT, 10), fg=C_TEXT, bg=C_BG,
                 justify="center").pack()
        tk.Label(f, text="v2.0  ·  Windows 7 / 8 / 10 / 11",
                 font=(FNT, 8), fg=C_GRAY, bg=C_BG).pack(pady=(20, 0))

    # ── Página 2: Requisitos ──────────────────────────────────────────────────
    def _pg_requisitos(self):
        f = tk.Frame(self.content, bg=C_BG, padx=32, pady=16)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="Verificación de requisitos", font=(FNT, 12, "bold"),
                 fg=C_TEXT, bg=C_BG).pack(anchor="w")
        tk.Label(f, text="El sistema verificará e instalará lo necesario automáticamente.",
                 font=(FNT, 9), fg=C_GRAY, bg=C_BG).pack(anchor="w", pady=(2,12))

        items = [
            ("python",    "Python " + sys.version.split()[0]),
            ("internet",  "Conexión a internet"),
            ("agente",    "Archivo mir_agente.py"),
            ("speedtest", "Speedtest CLI"),
            ("psutil",    "Monitor de hardware (psutil)"),
        ]
        self._req_labels = {}
        for key, label in items:
            row = tk.Frame(f, bg=C_WHITE, relief="flat", bd=0)
            row.pack(fill="x", pady=3, ipady=6)
            tk.Frame(row, bg=C_GOLD, width=4).pack(side="left", fill="y")
            tk.Label(row, text=label, font=(FNT, 10), fg=C_TEXT,
                     bg=C_WHITE, padx=12).pack(side="left")
            lbl_st = tk.Label(row, text="Pendiente", font=(FNT, 9),
                              fg=C_GRAY, bg=C_WHITE, padx=8)
            lbl_st.pack(side="right")
            self._req_labels[key] = lbl_st

        btn = tk.Button(f, text="▶  Verificar e instalar", font=(FNT, 10, "bold"),
                        fg=C_WHITE, bg=C_HEADER, relief="flat", bd=0,
                        cursor="hand2", padx=16, pady=8,
                        command=lambda: threading.Thread(
                            target=self._run_requisitos, daemon=True).start())
        btn.pack(pady=(14,0), anchor="w")

        self._lbl_req_ok = tk.Label(f, text="", font=(FNT, 10, "bold"),
                                    fg=C_VERDE, bg=C_BG)
        self._lbl_req_ok.pack(anchor="w", pady=(6,0))

        self.btn_next.config(state="disabled")
        self._req_ok = False

    def _set_req(self, key, ok, texto=None):
        lbl = self._req_labels.get(key)
        if not lbl:
            return
        if ok:
            lbl.config(text=texto or "✓ OK", fg=C_VERDE)
        else:
            lbl.config(text=texto or "✗ Fallo", fg=C_ROJO)

    def _run_requisitos(self):
        import urllib.request as _ur
        todo_ok = True

        # Python (siempre OK si estamos acá)
        self.root.after(0, lambda: self._set_req("python", True,
            "✓ " + sys.version.split()[0]))

        # Conexión a internet
        try:
            _ur.urlopen("https://www.google.com", timeout=5)
            self.root.after(0, lambda: self._set_req("internet", True, "✓ Disponible"))
        except Exception:
            self.root.after(0, lambda: self._set_req("internet", False,
                "✗ Sin conexión — verificá el cable/WiFi"))
            todo_ok = False

        # mir_agente.py
        agente_ok = os.path.exists(AGENT_FILE)
        self.root.after(0, lambda: self._set_req("agente", agente_ok,
            "✓ Encontrado" if agente_ok else "✗ No encontrado — copialo a esta carpeta"))
        if not agente_ok:
            todo_ok = False

        # speedtest
        if pkg_instalado("speedtest"):
            self.root.after(0, lambda: self._set_req("speedtest", True, "✓ Instalado"))
        else:
            self.root.after(0, lambda: self._set_req("speedtest", None, "⟳ Instalando..."))
            ok_s = instalar_pkg("speedtest-cli", lambda m: None)
            self.root.after(0, lambda ok=ok_s: self._set_req(
                "speedtest", ok, "✓ Instalado" if ok else "✗ Error al instalar"))
            if not ok_s:
                todo_ok = False

        # psutil (hardware monitoring)
        if pkg_instalado("psutil"):
            self.root.after(0, lambda: self._set_req("psutil", True, "✓ Instalado"))
        else:
            self.root.after(0, lambda: self._set_req("psutil", None, "⟳ Instalando..."))
            ok_p = instalar_pkg("psutil", lambda m: None)
            self.root.after(0, lambda ok=ok_p: self._set_req(
                "psutil", ok, "✓ Instalado" if ok else "✗ Error al instalar"))
            if not ok_p:
                todo_ok = False

        if todo_ok:
            self._req_ok = True
            self.root.after(0, lambda: self.btn_next.config(state="normal"))
            self.root.after(0, lambda: self._lbl_req_ok.config(
                text="✓ Todo listo — avanzando..."))
            self.root.after(1500, self._next)
        else:
            self.root.after(0, lambda: self._lbl_req_ok.config(
                text="✗ Corregí los errores y volvé a verificar.", fg=C_ROJO))

    # ── Página 3: Datos del cliente ───────────────────────────────────────────
    def _pg_cliente(self):
        self._clientes_map = {}  # display label → cliente_id

        f = tk.Frame(self.content, bg=C_BG, padx=32, pady=16)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="Seleccionar cliente", font=(FNT, 12, "bold"),
                 fg=C_TEXT, bg=C_BG).pack(anchor="w")
        tk.Label(f, text="Elegí el cliente desde la lista registrada en el panel de administración.",
                 font=(FNT, 9), fg=C_GRAY, bg=C_BG).pack(anchor="w", pady=(2,12))

        tk.Label(f, text="Cliente *", font=(FNT, 9, "bold"),
                 fg=C_TEXT, bg=C_BG).pack(anchor="w", pady=(0,2))

        self._v_combo = tk.StringVar()
        self._combo = ttk.Combobox(f, textvariable=self._v_combo,
                                    font=(FNT, 10), state="readonly")
        self._combo.pack(fill="x", ipady=4)
        self._combo.bind("<<ComboboxSelected>>", self._on_cliente_seleccionado)

        self._lbl_cliente_st = tk.Label(f, text="Cargando lista...",
                                         font=(FNT, 9), fg=C_GRAY, bg=C_BG)
        self._lbl_cliente_st.pack(anchor="w", pady=(4,0))

        tk.Label(f, text="ID asignado:", font=(FNT, 9, "bold"),
                 fg=C_TEXT, bg=C_BG).pack(anchor="w", pady=(16,2))
        tk.Entry(f, textvariable=self.v_id, font=("Consolas", 10),
                 relief="solid", bd=1, fg=C_HEADER,
                 state="readonly").pack(fill="x", ipady=5)

        btn_row = tk.Frame(f, bg=C_BG)
        btn_row.pack(anchor="w", pady=(10,0))
        tk.Button(btn_row, text="Recargar lista", font=(FNT, 9),
                  fg=C_WHITE, bg="#374151", relief="flat", bd=0,
                  padx=10, pady=4, cursor="hand2",
                  command=self._cargar_clientes).pack(side="left")

        # carga automática al entrar a la página
        self.root.after(100, self._cargar_clientes)

    def _cargar_clientes(self):
        self._lbl_cliente_st.config(text="Cargando lista...", fg=C_GRAY)
        self._combo.config(state="disabled")
        def run():
            clientes, err = fetch_clientes(AGENTE_EMAIL, AGENTE_CONTRASENA)
            def update():
                if err or not clientes:
                    msg = f"Error al conectar: {err[:60]}" if err else "No hay clientes registrados."
                    self._lbl_cliente_st.config(text=msg, fg=C_ROJO)
                    self._combo.config(state="readonly")
                    return
                self._clientes_map = {
                    f"{c['nombre']}  ({c['cliente_id']})": c["cliente_id"]
                    for c in clientes
                }
                self._combo["values"] = list(self._clientes_map.keys())
                self._combo.config(state="readonly")
                self._lbl_cliente_st.config(
                    text=f"{len(clientes)} cliente(s) encontrado(s).", fg=C_VERDE)
                # si ya había uno seleccionado, mantenerlo
                if self.v_id.get():
                    for label, cid in self._clientes_map.items():
                        if cid == self.v_id.get():
                            self._v_combo.set(label)
                            break
            self.root.after(0, update)
        threading.Thread(target=run, daemon=True).start()

    def _on_cliente_seleccionado(self, event):
        label = self._v_combo.get()
        self.v_id.set(self._clientes_map.get(label, ""))

    # ── Página 4: Cámaras / NVR ───────────────────────────────────────────────
    def _pg_camaras(self):
        f = tk.Frame(self.content, bg=C_BG, padx=32, pady=14)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="Sistema de cámaras / NVR", font=(FNT, 12, "bold"),
                 fg=C_TEXT, bg=C_BG).pack(anchor="w")
        tk.Label(f, text="Opcional. Si el cliente tiene DVR o NVR, configuralo acá.",
                 font=(FNT, 9), fg=C_GRAY, bg=C_BG).pack(anchor="w", pady=(2,8))

        chk = tk.Checkbutton(f, text="El cliente tiene sistema de cámaras",
                             variable=self.v_tiene_cam, font=(FNT, 10),
                             bg=C_BG, fg=C_TEXT, activebackground=C_BG,
                             command=self._toggle_cam_form)
        chk.pack(anchor="w")

        self._cam_form = tk.Frame(f, bg=C_BG)
        self._cam_form.pack(fill="both", expand=True, pady=(8,0))
        self._build_cam_form()
        self._toggle_cam_form()

    def _toggle_cam_form(self):
        state = "normal" if self.v_tiene_cam.get() else "disabled"
        def set_state(widget):
            for w in widget.winfo_children():
                try:
                    w.configure(state=state)
                except tk.TclError:
                    pass  # Frame y otros contenedores no tienen state
                set_state(w)  # recursivo para widgets anidados
        set_state(self._cam_form)

    def _build_cam_form(self):
        frm = self._cam_form
        def lbl(txt): tk.Label(frm, text=txt, font=(FNT, 9, "bold"),
                                fg=C_TEXT, bg=C_BG).grid(sticky="w", pady=(6,1))
        def ent(var, **kw):
            e = tk.Entry(frm, textvariable=var, font=(FNT, 9),
                         relief="solid", bd=1, **kw)
            e.grid(sticky="ew", ipady=4)
            return e
        frm.columnconfigure(0, weight=1)

        lbl("Nombre del equipo")
        ent(self.v_cam_nom)
        lbl("Marca")
        mb = ttk.Combobox(frm, textvariable=self.v_cam_marca,
                           values=["hikvision", "dahua", "intelbras"], font=(FNT, 9), state="readonly")
        mb.grid(sticky="ew")
        lbl("IP del NVR/DVR")
        ent(self.v_cam_ip)
        tk.Label(frm, text="⚠ Ingresar IP del NVR/DVR, no de cámaras individuales",
                 font=(FNT, 8), fg="#e0a800", bg=C_BG).grid(sticky="w")

        cols = tk.Frame(frm, bg=C_BG)
        cols.grid(sticky="ew", pady=(6,0))
        cols.columnconfigure(0, weight=2)
        cols.columnconfigure(1, weight=2)
        cols.columnconfigure(2, weight=1)
        tk.Label(cols, text="Usuario", font=(FNT, 9, "bold"),
                 fg=C_TEXT, bg=C_BG).grid(row=0, column=0, sticky="w")
        tk.Label(cols, text="Contraseña", font=(FNT, 9, "bold"),
                 fg=C_TEXT, bg=C_BG).grid(row=0, column=1, sticky="w", padx=(8,0))
        tk.Label(cols, text="Puerto", font=(FNT, 9, "bold"),
                 fg=C_TEXT, bg=C_BG).grid(row=0, column=2, sticky="w", padx=(8,0))
        tk.Entry(cols, textvariable=self.v_cam_user, font=(FNT, 9),
                 relief="solid", bd=1).grid(row=1, column=0, sticky="ew", ipady=4)
        tk.Entry(cols, textvariable=self.v_cam_pass, font=(FNT, 9),
                 relief="solid", bd=1, show="*").grid(row=1, column=1, sticky="ew",
                 ipady=4, padx=(8,0))
        tk.Entry(cols, textvariable=self.v_cam_port, font=(FNT, 9),
                 relief="solid", bd=1, width=6).grid(row=1, column=2, sticky="ew",
                 ipady=4, padx=(8,0))

        btns = tk.Frame(frm, bg=C_BG)
        btns.grid(sticky="w", pady=(10,0))
        tk.Button(btns, text="Probar conexión", font=(FNT, 9), fg=C_WHITE,
                  bg="#2563eb", relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=self._probar_cam).pack(side="left")
        tk.Button(btns, text="+ Agregar equipo", font=(FNT, 9), fg=C_WHITE,
                  bg=C_VERDE, relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=self._agregar_cam).pack(side="left", padx=(8,0))
        self._lbl_cam_st = tk.Label(btns, text="", font=(FNT, 9), bg=C_BG)
        self._lbl_cam_st.pack(side="left", padx=8)

        self._lbl_cams = tk.Label(frm, text=self._resumen_cams(),
                                   font=(FNT, 9), fg=C_GRAY, bg=C_BG, justify="left")
        self._lbl_cams.grid(sticky="w", pady=(6,0))

    def _resumen_cams(self):
        if not self.camaras:
            return "Sin equipos agregados aún."
        return "\n".join(f"  ✓ {c['nombre']}  ({c['ip']})" for c in self.camaras)

    def _probar_cam(self):
        cfg = {"nombre": self.v_cam_nom.get(), "marca": self.v_cam_marca.get(),
               "ip": self.v_cam_ip.get(), "usuario": self.v_cam_user.get(),
               "password": self.v_cam_pass.get(), "puerto": int(self.v_cam_port.get() or 80)}
        self._lbl_cam_st.config(text="Probando...", fg=C_GRAY)
        def run():
            ok, err = test_camara(cfg)
            msg = "✓ Conexión exitosa" if ok else f"✗ {err[:40]}"
            col = C_VERDE if ok else C_ROJO
            self.root.after(0, lambda: self._lbl_cam_st.config(text=msg, fg=col))
        threading.Thread(target=run, daemon=True).start()

    def _agregar_cam(self):
        if not self.v_cam_ip.get():
            messagebox.showwarning("Dato requerido", "Ingresá la IP del equipo.")
            return
        self.camaras.append({
            "nombre":   self.v_cam_nom.get() or f"NVR {len(self.camaras)+1}",
            "marca":    self.v_cam_marca.get(),
            "ip":       self.v_cam_ip.get(),
            "usuario":  self.v_cam_user.get(),
            "password": self.v_cam_pass.get(),
            "puerto":   int(self.v_cam_port.get() or 80)
        })
        self.v_cam_nom.set(""); self.v_cam_ip.set("")
        self.v_cam_pass.set(""); self.v_cam_port.set("80")
        self._lbl_cams.config(text=self._resumen_cams(), fg=C_VERDE)
        self._lbl_cam_st.config(text=f"{len(self.camaras)} equipo(s) agregado(s)", fg=C_VERDE)

    # ── Página 5: Instalación ─────────────────────────────────────────────────
    def _pg_instalar(self):
        self.btn_next.config(state="disabled")
        self.btn_back.config(state="disabled")

        f = tk.Frame(self.content, bg=C_BG, padx=32, pady=14)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="Instalando...", font=(FNT, 12, "bold"),
                 fg=C_TEXT, bg=C_BG).pack(anchor="w")

        self._prog = ttk.Progressbar(f, mode="determinate", maximum=100)
        self._prog.pack(fill="x", pady=(10,8))

        self._log = tk.Text(f, font=("Consolas", 8), height=10,
                            bg="#1a1a2e", fg="#e0e0e0", relief="flat",
                            state="disabled", wrap="word")
        self._log.pack(fill="both", expand=True)

        tk.Checkbutton(f, text="Iniciar agente automáticamente al encender el equipo",
                       variable=self.v_autostart, font=(FNT, 9),
                       bg=C_BG, fg=C_TEXT, activebackground=C_BG).pack(anchor="w", pady=(8,0))

        threading.Thread(target=self._run_install, daemon=True).start()

    def _log_write(self, msg, color="#e0e0e0"):
        def _do():
            self._log.config(state="normal")
            self._log.insert("end", msg + "\n")
            self._log.config(state="disabled")
            self._log.see("end")
        self.root.after(0, _do)

    def _set_prog(self, val):
        self.root.after(0, lambda: self._prog.config(value=val))

    def _run_install(self):
        import shutil
        pasos = 8
        paso_val = 100 // pasos

        # 0. Detener agente anterior si está corriendo
        self._log_write("▶ Deteniendo agente anterior (si existe)...")
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/IM", "pythonw.exe"],
                capture_output=True, text=True
            )
            if r.returncode == 0:
                self._log_write("  Agente anterior detenido ✓")
                import time; time.sleep(1)  # esperar que libere archivos
            else:
                self._log_write("  Sin agente previo en ejecución ✓")
        except Exception as e:
            self._log_write(f"  (No se pudo verificar proceso previo: {e})")
        self._set_prog(paso_val)

        # 1. Dependencias
        self._log_write("▶ Verificando dependencias Python...")
        if not pkg_instalado("speedtest"):
            self._log_write("  Instalando speedtest-cli...")
            instalar_pkg("speedtest-cli", self._log_write)
        else:
            self._log_write("  speedtest-cli: ya instalado ✓")
        self._set_prog(paso_val)

        # 2. Crear directorio de instalación y copiar archivos
        self._log_write(f"▶ Instalando en {INSTALL_DIR}...")
        try:
            os.makedirs(INSTALL_DIR, exist_ok=True)
            shutil.copy2(AGENT_FILE, os.path.join(INSTALL_DIR, "mir_agente.py"))
            if os.path.exists(DESINT_FILE):
                shutil.copy2(DESINT_FILE, os.path.join(INSTALL_DIR, "mir_desinstalador.bat"))
            self._log_write(f"  Archivos copiados a {INSTALL_DIR} ✓")
        except Exception as e:
            self._log_write(f"  Error al copiar archivos: {e}")
        self._set_prog(paso_val * 2)

        # 3. Guardar config
        self._log_write("▶ Guardando configuración del cliente...")
        cfg = {
            "cliente_id":        self.v_id.get(),
            "firebase_url":      FIREBASE_URL,
            "firebase_api_key":  FIREBASE_API_KEY,
            "intervalo_seg":     60,
            "intervalo_escaneo": 300
        }
        with open(os.path.join(INSTALL_DIR, "mir_config.json"), "w", encoding="utf-8") as fp:
            json.dump(cfg, fp, indent=2, ensure_ascii=False)
        self._log_write("  mir_config.json guardado ✓")
        self._set_prog(paso_val * 3)

        # 4. Guardar cámaras
        self._log_write("▶ Guardando configuración de cámaras...")
        cams = self.camaras if self.v_tiene_cam.get() else []
        with open(os.path.join(INSTALL_DIR, "mir_camaras.json"), "w", encoding="utf-8") as fp:
            json.dump(cams, fp, indent=2, ensure_ascii=False)
        self._log_write(f"  mir_camaras.json guardado ({len(cams)} equipo(s)) ✓")
        self._set_prog(paso_val * 4)

        # 5. Test Firebase con credenciales del agente compartido
        self._log_write("▶ Verificando conexión a Firebase...")
        ok_fb, err_fb = test_firebase(
            self.v_id.get(), AGENTE_EMAIL, AGENTE_CONTRASENA)
        if ok_fb:
            self._log_write("  Conexión a Firebase: OK ✓")
        else:
            self._log_write(f"  Firebase: advertencia — {err_fb[:80]}")
            self._log_write("  (El agente reintentará automáticamente al iniciar)")
        self._set_prog(paso_val * 5)

        # 6. Excluir de Windows Defender (reduce falsos positivos)
        self._log_write("▶ Configurando exclusión en Windows Defender...")
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 f'Add-MpPreference -ExclusionPath "{INSTALL_DIR}"'],
                capture_output=True, text=True, timeout=20
            )
            if r.returncode == 0:
                self._log_write("  Exclusión de Defender configurada ✓")
            else:
                self._log_write("  Defender: sin permisos de admin (no crítico)")
        except Exception:
            self._log_write("  Defender: omitido (no disponible en este sistema)")
        self._set_prog(paso_val * 6)

        # 7. Autostart
        if self.v_autostart.get():
            self._log_write("▶ Configurando inicio automático...")
            ok_at, metodo = configurar_autostart(self.v_id.get(), INSTALL_DIR)
            if ok_at:
                self._log_write(f"  Inicio automático configurado: {metodo} ✓")
            else:
                self._log_write("  Sin permisos para Programador de tareas.")
                self._log_write("  Alternativa: agregá el .bat a la carpeta Inicio manualmente.")

        self._set_prog(100)
        self._log_write("\n✓ Instalación completada.")
        self._install_ok = True
        self.root.after(0, lambda: self.btn_next.config(state="normal",
            text="Ver resumen →"))
        self.root.after(0, lambda: self.btn_back.config(state="disabled"))

    # ── Página 6: Listo ───────────────────────────────────────────────────────
    def _pg_listo(self):
        f = tk.Frame(self.content, bg=C_BG)
        f.pack(expand=True)

        tk.Label(f, text="✓", font=(FNT, 36, "bold"), fg=C_VERDE, bg=C_BG).pack(pady=(20,4))
        tk.Label(f, text="¡Instalación completada!", font=(FNT, 14, "bold"),
                 fg=C_TEXT, bg=C_BG).pack()
        tk.Frame(f, bg=C_GOLD, height=2, width=160).pack(pady=10)

        info = (f"  ID:         {self.v_id.get()}\n"
                f"  Instalado en: {INSTALL_DIR}\n"
                f"  Cámaras:    {len(self.camaras)} equipo(s)\n"
                f"  Autostart:  {'Sí' if self.v_autostart.get() else 'No'}")
        tk.Label(f, text=info, font=("Consolas", 9), fg=C_TEXT, bg=C_WHITE,
                 justify="left", padx=16, pady=10, relief="flat").pack(pady=(0,14))

        btns = tk.Frame(f, bg=C_BG)
        btns.pack()
        tk.Button(btns, text="Abrir Dashboard", font=(FNT, 10), fg=C_WHITE,
                  bg="#2563eb", relief="flat", bd=0, padx=14, pady=8,
                  cursor="hand2",
                  command=lambda: webbrowser.open(DASHBOARD_URL)
                  ).pack(side="left", padx=4)
        tk.Button(btns, text="Iniciar agente ahora", font=(FNT, 10), fg=C_WHITE,
                  bg=C_VERDE, relief="flat", bd=0, padx=14, pady=8,
                  cursor="hand2", command=self._iniciar_agente).pack(side="left", padx=4)

        self.btn_next.config(text="Cerrar", state="normal")

    def _iniciar_agente(self):
        try:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            agent_installed = os.path.join(INSTALL_DIR, "mir_agente.py")
            subprocess.Popen([pythonw, agent_installed], cwd=INSTALL_DIR, env=env)
            messagebox.showinfo("Agente iniciado",
                "El agente de monitoreo está corriendo en segundo plano.\n"
                "Los datos comenzarán a aparecer en el dashboard en ~60 segundos.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run(self):
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Instalador()
    app.run()
