"""
Mir Soluciones — Gestión de usuarios del dashboard
===================================================
Crea, lista y elimina usuarios que pueden acceder
al dashboard de cliente (index.html).

Ejecutar: python mir_add_usuario.py
"""

import os
import sys
import json
import subprocess

DIR        = os.path.dirname(os.path.abspath(__file__))
CFG_PATH   = os.path.join(DIR, "mir_config.json")

# ─────────────────────────────────────────────
#  CARGAR CONFIG
# ─────────────────────────────────────────────

def cargar_config():
    if not os.path.exists(CFG_PATH):
        print("\n  [!] No se encontró mir_config.json.")
        print("      Corré primero mir_setup.py.\n")
        sys.exit(1)
    with open(CFG_PATH, encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────────────────────────────
#  INSTALAR firebase-admin SI FALTA
# ─────────────────────────────────────────────

def asegurar_firebase_admin():
    try:
        import firebase_admin  # noqa
    except ImportError:
        print("  [..] Instalando firebase-admin...", end=" ", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "firebase-admin", "--quiet"],
            timeout=120
        )
        print("OK")

# ─────────────────────────────────────────────
#  FIREBASE ADMIN
# ─────────────────────────────────────────────

_admin_app = None

def iniciar_admin(cfg):
    global _admin_app
    if _admin_app:
        return
    import firebase_admin
    from firebase_admin import credentials
    cred = credentials.Certificate(cfg["clave_json"])
    _admin_app = firebase_admin.initialize_app(cred, {
        "databaseURL": cfg["firebase_url"]
    })

def listar_usuarios(cfg):
    from firebase_admin import auth, db
    print()
    print("  ─────────────────────────────────────────────────────")
    print(f"  {'EMAIL':<35} {'CLIENTE ID':<20} {'CREADO'}")
    print("  ─────────────────────────────────────────────────────")

    page = auth.list_users()
    total = 0
    while page:
        for u in page.users:
            # Buscar cliente_id en la DB
            snap = db.reference(f"usuarios/{u.uid}/cliente_id").get()
            cliente_id = snap or "(sin asignar)"
            creado = u.user_metadata.creation_timestamp
            import datetime
            fecha = datetime.datetime.fromtimestamp(creado / 1000).strftime("%d/%m/%Y") if creado else "—"
            print(f"  {u.email:<35} {cliente_id:<20} {fecha}")
            total += 1
        page = page.get_next_page()

    if total == 0:
        print("  (no hay usuarios registrados)")
    print("  ─────────────────────────────────────────────────────")
    print(f"  Total: {total} usuario(s)")
    print()

def crear_usuario(cfg):
    from firebase_admin import auth, db

    print()
    print("  Ingresá los datos del nuevo usuario:")
    print()

    # Email
    while True:
        email = input("  Email: ").strip()
        if "@" in email and "." in email:
            break
        print("  Email inválido. Intentá de nuevo.")

    # Contraseña
    while True:
        pwd = input("  Contraseña (mín. 6 caracteres): ").strip()
        if len(pwd) >= 6:
            break
        print("  La contraseña debe tener al menos 6 caracteres.")

    # Cliente ID
    print()
    print("  ¿A qué cliente corresponde este usuario?")
    # Mostrar clientes disponibles en Firebase
    clientes = db.reference("clientes").get() or {}
    if clientes:
        print("  Clientes en Firebase:")
        for k in sorted(clientes.keys()):
            print(f"    · {k}")
    print()
    cliente_id = input("  Cliente ID: ").strip()
    if not cliente_id:
        print("  [!] Cliente ID requerido.")
        return

    # Crear usuario en Firebase Auth
    print()
    print("  [..] Creando usuario...", end=" ", flush=True)
    try:
        user = auth.create_user(email=email, password=pwd)
        print("OK ✓")
    except Exception as e:
        print(f"FALLO\n  [!] {e}")
        return

    # Guardar mapping uid → cliente_id en la DB
    print("  [..] Vinculando con cliente...", end=" ", flush=True)
    try:
        db.reference(f"usuarios/{user.uid}").set({
            "cliente_id": cliente_id,
            "email":      email
        })
        print("OK ✓")
    except Exception as e:
        print(f"FALLO\n  [!] {e}")
        return

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║  Usuario creado correctamente            ║")
    print("  ╠══════════════════════════════════════════╣")
    print(f"  ║  Email    : {email:<30}║")
    print(f"  ║  Contraseña: {pwd:<29}║")
    print(f"  ║  Cliente  : {cliente_id:<30}║")
    print("  ╚══════════════════════════════════════════╝")
    print()
    print("  Entregale el email y la contraseña al cliente.")
    print(f"  URL de acceso: https://mir-soluciones-35859.web.app")
    print()

def eliminar_usuario(cfg):
    from firebase_admin import auth, db

    print()
    email = input("  Email del usuario a eliminar: ").strip()
    if not email:
        return

    try:
        user = auth.get_user_by_email(email)
    except Exception:
        print(f"  [!] No se encontró el usuario: {email}")
        return

    confirmar = input(f"  ¿Eliminar {email}? (s/n): ").strip().lower()
    if confirmar not in ("s", "si", "sí"):
        print("  Cancelado.")
        return

    print("  [..] Eliminando...", end=" ", flush=True)
    try:
        auth.delete_user(user.uid)
        db.reference(f"usuarios/{user.uid}").delete()
        print("OK ✓")
        print(f"  Usuario {email} eliminado.")
    except Exception as e:
        print(f"FALLO\n  [!] {e}")
    print()

# ─────────────────────────────────────────────
#  MENÚ PRINCIPAL
# ─────────────────────────────────────────────

asegurar_firebase_admin()
cfg = cargar_config()
iniciar_admin(cfg)

print()
print("  ══════════════════════════════════════════")
print("  Mir Soluciones — Gestión de usuarios")
print("  ══════════════════════════════════════════")

while True:
    print()
    print("  1. Listar usuarios")
    print("  2. Crear usuario")
    print("  3. Eliminar usuario")
    print("  4. Salir")
    print()
    opcion = input("  Opción: ").strip()

    if opcion == "1":
        listar_usuarios(cfg)
    elif opcion == "2":
        crear_usuario(cfg)
    elif opcion == "3":
        eliminar_usuario(cfg)
    elif opcion == "4":
        break
    else:
        print("  Opción inválida.")
