#!/usr/bin/env python3
"""
Envía el mensaje (texto + imágenes) a grupos de WhatsApp vía Evolution API.

Modos de uso:
  python3 enviar_grupos.py              → envía a TODOS los grupos del CSV
  python3 enviar_grupos.py --desde 10  → reanuda desde la fila 10 (útil si se interrumpió)
"""

import csv, base64, time, sys, requests
from pathlib import Path

# ── Configuración ──────────────────────────────────────────────────────────────
API_URL      = "https://whatsapp-api.jhonocampo.com"
API_KEY      = "f6c84b78359e1990412b8aa2f5b36ebd1b864615793640f7cc9c3a49ecddb92c"
INSTANCE     = "Chinatowm"
MSG_DIR      = Path("/mnt/disco960/proyectos/whatsapp/mensaje")
CSV_FILE     = Path("/home/jhonandmary/grupos_chinatowm.csv")
LOG_FILE     = Path("/mnt/disco960/proyectos/whatsapp/envio_log.csv")
DELAY_SEG    = 8   # segundos entre grupos para evitar bloqueos
# ──────────────────────────────────────────────────────────────────────────────

HEADERS = {"apikey": API_KEY, "Content-Type": "application/json"}


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
    desde = 1
    if "--desde" in sys.argv:
        idx = sys.argv.index("--desde")
        desde = int(sys.argv[idx + 1])

    texto = (MSG_DIR / "msg.txt").read_text(encoding="utf-8").strip()
    imagenes = sorted(MSG_DIR.glob("*.jpeg")) + sorted(MSG_DIR.glob("*.jpg"))
    grupos   = cargar_grupos(desde)

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
