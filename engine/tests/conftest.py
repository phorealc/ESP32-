from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard_engine.config import Config
from dashboard_engine.server import create_app


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Config isolee : toutes les sources reseau sont desactivees.

    Les tests d'API ne doivent jamais sortir sur Internet ; les modules
    concernes se replient donc sur `DisabledSource`.
    """
    cfg = Config()
    cfg.base_dir = tmp_path
    cfg.music.enabled = False
    cfg.minecraft.enabled = False
    cfg.weather.enabled = False
    cfg.stream.enabled = False
    cfg.checklist.path = "checklist.json"
    cfg.checklist.default_items = ["Lancer OBS", "Verifier le micro"]
    return cfg


@pytest.fixture
def client(config: Config):
    with TestClient(create_app(config)) as test_client:
        yield test_client
