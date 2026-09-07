# -*- mode: python ; coding: utf-8 -*-
"""Empaquetage du moteur en binaire autonome (sidecar de la coquille Tauri).

Construction :  pyinstaller dashboard-engine.spec --noconfirm
Resultat     :  dist/dashboard-engine[.exe]

Le binaire n'embarque pas de configuration : au premier lancement il ecrit un
`config.toml` commente dans le dossier utilisateur (voir `config.py`).
"""

import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Le modele de configuration doit voyager avec le binaire : c'est lui qui sert
# a creer le config.toml de l'utilisateur au premier lancement.
datas = [("dashboard_engine/config.example.toml", "dashboard_engine")]
binaries = []
hiddenimports = []

# uvicorn choisit ses boucles et ses protocoles par import dynamique
# (`uvicorn.protocols.http.auto`...) : PyInstaller ne peut pas les deduire de
# l'analyse statique, il faut les collecter explicitement. Meme logique pour
# mcstatus, qui charge ses resolveurs DNS a l'execution.
for package in ("uvicorn", "mcstatus", "dns"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += collect_submodules("websockets")
hiddenimports += collect_submodules("anyio")

# L'API media de Windows n'existe que sur Windows ; l'inclure ailleurs
# ferait echouer l'analyse.
if sys.platform == "win32":
    winsdk_datas, winsdk_binaries, winsdk_hidden = collect_all("winsdk")
    datas += winsdk_datas
    binaries += winsdk_binaries
    hiddenimports += winsdk_hidden

analysis = Analysis(
    ["dashboard_engine/__main__.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Tkinter et les bibliotheques scientifiques n'ont rien a faire ici : les
    # exclure fait gagner plusieurs dizaines de Mio.
    excludes=["tkinter", "unittest", "pytest", "numpy", "matplotlib", "PIL"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="dashboard-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # `console=True` : la sortie doit rester un vrai flux pour que Tauri lise
    # les logs du sidecar. Aucune fenetre n'apparait pour autant — Tauri lance
    # ses sidecars avec CREATE_NO_WINDOW sous Windows.
    console=True,
    disable_windowed_traceback=False,
    codesign_identity=None,
    entitlements_file=None,
)
