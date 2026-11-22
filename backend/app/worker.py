"""Ejecuta trabajos solo cuando existen peticiones de analisis."""
import argparse
import time
from . import db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Procesar como maximo un trabajo y salir")
    parser.add_argument("--interval", type=float, default=1.0, help="Segundos entre comprobaciones")
    args = parser.parse_args()
    path = db.db_path()
    db.init_db(path)
    while True:
        processed = db.process_one(path)
        if processed:
            print(f"Trabajo procesado: {processed}", flush=True)
        if args.once:
            break
        if not processed:
            time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    main()
