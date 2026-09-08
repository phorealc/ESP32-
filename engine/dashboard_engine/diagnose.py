"""Outil de diagnostic : interroge une source et affiche ses reponses brutes.

    python -m dashboard_engine.diagnose streamlabs
    python -m dashboard_engine.diagnose obs

L'API de Streamlabs Desktop n'est pas versionnee et ses champs bougent d'une
version a l'autre. Plutot que de deviner, cette commande montre ce que **votre**
installation renvoie reellement : si l'onglet Stream affiche des valeurs vides,
c'est ici qu'on voit pourquoi.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from dashboard_engine.config import Config, load_config

# Services interroges, avec la methode JSON-RPC associee.
STREAMLABS_PROBES = [
    ("getModel", "StreamingService"),
    ("activeScene", "ScenesService"),
    ("getModel", "PerformanceService"),
    ("getScenes", "ScenesService"),
]

OBS_PROBES = ["GetStreamStatus", "GetRecordStatus", "GetCurrentProgramScene", "GetStats"]

PREVIEW_CHARS = 4000
"""Les reponses de Streamlabs peuvent etre longues (liste des scenes) ; on les
tronque pour garder une sortie lisible dans un terminal."""


def show(title: str, payload: object) -> None:
    print(f"\n--- {title} ---")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:PREVIEW_CHARS])
    else:
        print(repr(payload))


async def diagnose_streamlabs(config: Config) -> int:
    from dashboard_engine.sources.streamlabs_desktop import StreamlabsDesktopClient

    broadcaster = config.stream.broadcaster
    client = StreamlabsDesktopClient(
        token=broadcaster.token,
        host=broadcaster.host,
        port=broadcaster.port,
        use_pipe=broadcaster.use_pipe,
    )
    print(
        f"Streamlabs Desktop — tube nomme: {broadcaster.use_pipe}, "
        f"TCP: {broadcaster.host}:{broadcaster.port}, "
        f"jeton: {'oui' if broadcaster.token else 'non'}"
    )

    failures = 0
    for method, resource in STREAMLABS_PROBES:
        try:
            result = await client.request(method, resource)
            show(f"{resource}.{method}()  [transport: {client.transport}]", result)
        except Exception as exc:
            failures += 1
            print(f"\n--- {resource}.{method}() ---\nECHEC: {type(exc).__name__}: {exc}")
    await client.close()

    if failures == len(STREAMLABS_PROBES):
        print(
            "\nAucun service n'a repondu. Verifiez que Streamlabs Desktop est lance, puis :\n"
            "  - sous Windows, le tube nomme suffit normalement ;\n"
            "  - sinon activez Parametres > Remote Control et copiez le jeton dans\n"
            "    [stream.broadcaster].token de votre config.toml."
        )
        return 1

    print(
        "\nComparez les champs ci-dessus a ceux que lit build_state() dans\n"
        "dashboard_engine/sources/streamlabs_desktop.py : streamingStatus,\n"
        "recordingStatus, name, frameRate, percentageDroppedFrames.\n"
        "S'ils different, ce sont ces constantes-la qu'il faut corriger."
    )
    return 0


async def diagnose_obs(config: Config) -> int:
    from dashboard_engine.sources.obs import ObsClient

    client = ObsClient(config.stream.broadcaster)
    print(f"OBS Studio — {config.stream.broadcaster.url}")
    try:
        for request in OBS_PROBES:
            show(request, await client.request(request))
    except Exception as exc:
        print(f"\nECHEC: {type(exc).__name__}: {exc}")
        print("Verifiez Outils > Parametres du serveur WebSocket dans OBS.")
        return 1
    finally:
        await client.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="dashboard-diagnose", description=__doc__)
    parser.add_argument("source", choices=["streamlabs", "obs"])
    parser.add_argument("--config", default=None, help="chemin du config.toml")
    args = parser.parse_args()

    config = load_config(args.config)
    runner = diagnose_streamlabs if args.source == "streamlabs" else diagnose_obs
    sys.exit(asyncio.run(runner(config)))


if __name__ == "__main__":
    main()
