"""Point d'entree du moteur : `python -m dashboard_engine`."""

from __future__ import annotations

import argparse
import logging
import socket
from pathlib import Path

import uvicorn

from dashboard_engine.config import DEFAULT_CONFIG_NAME, load_config
from dashboard_engine.server import create_app


def local_ip() -> str:
    """Adresse LAN de la machine, a renseigner dans le firmware ESP32.

    On ouvre un socket UDP vers une adresse externe sans rien emettre : cela
    force l'OS a choisir l'interface de sortie, y compris quand plusieurs cartes
    reseau existent (Wi-Fi + Ethernet + VM).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="dashboard-engine", description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=None, help=f"chemin du {DEFAULT_CONFIG_NAME}"
    )
    parser.add_argument("--host", default=None, help="adresse d'ecoute (surcharge la config)")
    parser.add_argument(
        "--port", type=int, default=None, help="port d'ecoute (surcharge la config)"
    )
    parser.add_argument("--log-level", default="info", help="debug, info, warning, error")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)
    host = args.host or config.server.host
    port = args.port or config.server.port

    if host in ("0.0.0.0", "::"):
        print(f"[dashboard] URL a renseigner dans l'ESP32 : http://{local_ip()}:{port}")

    uvicorn.run(create_app(config), host=host, port=port, log_level=args.log_level)


if __name__ == "__main__":
    main()
