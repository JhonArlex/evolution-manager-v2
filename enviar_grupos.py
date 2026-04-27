#!/usr/bin/env python3
"""
Envía el mensaje (texto + imágenes) a grupos de WhatsApp vía Evolution API.

Rutas (DATA_DIR: por defecto /app/data en contenedores con /app):
  msg.txt e imágenes: DATA_DIR/mensaje/  ó  sueltas en DATA_DIR/ (cualquiera)
  grupos: DATA_DIR/grupos_chinatowm.csv
  log:   DATA_DIR/envio_log.csv

Modos de uso:
  python3 enviar_grupos.py              → envía a TODOS los grupos del CSV
  python3 enviar_grupos.py --desde 10  → reanuda desde la fila 10 (útil si se interrumpió)
"""

import csv, base64, time, sys, os, requests
from pathlib import Path

# ── Configuración (entorno) ────────────────────────────────────────────────────
# En Docker: monta un volumen en DATA_DIR (p. ej. -v /ruta/host:/app/data).
#   Opción A — plano: /app/data/msg.txt, *.jpg, grupos_chinatowm.csv
#   Opción B — subcarpeta: /app/data/mensaje/msg.txt e imágenes
#
# Variables:
#   DATA_DIR   — raíz de datos (defecto: /app/data si existe /app, si no <script>/data)
#   MSG_DIR    — (opcional) carpeta con msg.txt; si no se pone, se detecta automáticamente
#   CSV_FILE   — CSV de grupos (defecto: $DATA_DIR/grupos_chinatowm.csv)
#   LOG_FILE   — log de envíos (defecto: $DATA_DIR/envio_log.csv)
#   API_URL, API_KEY, INSTANCE, DELAY_SEG

def _data_dir() -> Path:
    d = os.environ.get("DATA_DIR", "").strip()
    if d:
        return Path(d)
    # En Docker/Dokploy el volumen suele ir a /app/data. No usar solo __file__/data:
    # en cron el .py a veces está en otra ruta y el mount sigue en /app/data.
    if Path("/app").is_dir():
        return Path("/app/data")
    return Path(__file__).resolve().parent / "data"


DATA_DIR = _data_dir()
CSV_FILE = Path(os.environ.get("CSV_FILE", str(DATA_DIR / "grupos_chinatowm.csv")))
LOG_FILE = Path(os.environ.get("LOG_FILE", str(DATA_DIR / "envio_log.csv")))

API_URL = os.environ.get("API_URL", "https://whatsapp-api.jhonocampo.com").rstrip("/")
API_KEY = (os.environ.get("API_KEY") or os.environ.get("EVOLUTION_API_KEY") or "").strip()
INSTANCE = os.environ.get("INSTANCE", "Chinatowm")
DELAY_SEG = int(os.environ.get("DELAY_SEG", "8"))
# ──────────────────────────────────────────────────────────────────────────────

HEADERS = {"apikey": API_KEY, "Content-Type": "application/json"}


def resolve_msg_dir() -> Path:
    """
    Carpeta donde están msg.txt y las imágenes.
    Si MSG_DIR está en el entorno, se usa tal cual.
    Si no: prefiere DATA_DIR/mensaje si existe; si no, DATA_DIR si ahí está msg.txt (layout plano).
    """
    explicit = os.environ.get("MSG_DIR", "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_dir():
            return p
        print(f"MSG_DIR no es una carpeta existente: {p}", file=sys.stderr)
        sys.exit(1)

    nested = DATA_DIR / "mensaje"
    if nested.is_dir():
        return nested
    if (DATA_DIR / "msg.txt").is_file():
        return DATA_DIR

    hint_extra = _diagnostico_rutas()
    print(
        f"No hay mensaje en {nested} ni msg.txt en {DATA_DIR}.\n"
        f"  • En Dokploy: asigna un volumen a /app/data y sube msg.txt (y jpg) ahí, o bajo .../mensaje/\n"
        f"  • O en el job define DATA_DIR= la ruta real donde el volumen queda montado\n"
        f"  • O MSG_DIR= carpeta que contenga msg.txt\n{hint_extra}",
        file=sys.stderr,
    )
    sys.exit(1)


def _diagnostico_rutas() -> str:
    """Texto de ayuda con rutas reales (debug)."""
    lines = [f"  (script en {Path(__file__).resolve()!s}, DATA_DIR usado: {DATA_DIR!s})"]
    if not DATA_DIR.exists():
        lines.append(f"  DATA_DIR no existe aún: créala o monta el volumen en esa ruta.")
    elif DATA_DIR.is_dir():
        try:
            nombres = sorted(x.name for x in DATA_DIR.iterdir())[:25]
            lines.append(
                f"  Contenido de DATA_DIR: {nombres or '(vacía)'}" + (" …" if len(nombres) == 25 else "")
            )
        except OSError as e:
            lines.append(f"  No se pudo listar DATA_DIR: {e}")
    return "\n".join(lines)


def cargar_grupos(desde=1):
    grupos = []
    with open(CSV_FILE, encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            if i >= desde:
                grupos.append((i, row["ID"], row["Nombre"]))
    return grupos


def enviar_imagen(numero, imagen_path, caption=""):
    with open(imagen_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {
        "number": numero,
        "mediatype": "image",
        "mimetype": "image/jpeg",
        "media": b64,
        "fileName": imagen_path.name,
        "caption": caption,
    }
    r = requests.post(
        f"{API_URL}/message/sendMedia/{INSTANCE}",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )
    return r.status_code, r.json()


def registrar_log(fila, gid, nombre, estado):
    with open(LOG_FILE, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([fila, gid, nombre, estado])


def main():
    if not API_KEY:
        print("Falta API_KEY o EVOLUTION_API_KEY en el entorno.", file=sys.stderr)
        sys.exit(1)

    desde = 1
    if "--desde" in sys.argv:
        idx = sys.argv.index("--desde")
        desde = int(sys.argv[idx + 1])

    msg_dir = resolve_msg_dir()
    msg_path = msg_dir / "msg.txt"
    if not msg_path.is_file():
        print(f"No se encuentra {msg_path}", file=sys.stderr)
        sys.exit(1)
    if not CSV_FILE.is_file():
        print(f"No se encuentra el CSV: {CSV_FILE}", file=sys.stderr)
        sys.exit(1)

    texto = msg_path.read_text(encoding="utf-8").strip()
    imagenes = sorted(msg_dir.glob("*.jpeg")) + sorted(msg_dir.glob("*.jpg"))
    if not imagenes:
        print(f"No hay .jpg/.jpeg en {msg_dir}", file=sys.stderr)
        sys.exit(1)
    grupos   = cargar_grupos(desde)

    print(f"DATA_DIR={DATA_DIR} | msg_dir (mensaje)={msg_dir}")
    print(f"Mensaje: {len(texto)} caracteres | Imágenes: {len(imagenes)} | Grupos: {len(grupos)}")
    print(f"Tiempo estimado: ~{len(grupos) * DELAY_SEG // 60} min\n")

    # Crear encabezado del log si no existe
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["fila", "id", "nombre", "estado"])

    ok = err = 0
    for fila, gid, nombre in grupos:
        print(f"[{fila}/{fila + len(grupos) - 1}] {nombre[:55]}")

        try:
            # Primera imagen con caption (texto del mensaje)
            status, resp = enviar_imagen(gid, imagenes[0], caption=texto)
            if status == 201:
                # Imágenes restantes sin caption
                for img in imagenes[1:]:
                    enviar_imagen(gid, img)
                    time.sleep(2)
                registrar_log(fila, gid, nombre, "OK")
                print(f"  ✓ OK")
                ok += 1
            else:
                msg = resp.get("message") or resp.get("response", {}).get("message", str(resp))
                registrar_log(fila, gid, nombre, f"ERROR {status}: {msg}")
                print(f"  ✗ Error {status}: {msg}")
                err += 1
        except Exception as e:
            registrar_log(fila, gid, nombre, f"EXCEPCION: {e}")
            print(f"  ✗ Excepción: {e}")
            err += 1

        time.sleep(DELAY_SEG)

    print(f"\n✓ Completado — OK: {ok} | Errores: {err}")
    print(f"Log guardado en: {LOG_FILE}")


if __name__ == "__main__":
    main()
