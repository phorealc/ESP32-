from __future__ import annotations

import base64
import hashlib
import time

import pytest

from dashboard_engine.config import (
    BroadcasterConfig,
    MinecraftConfig,
    MinecraftServerConfig,
    MusicConfig,
    StreamConfig,
    WeatherConfig,
)
from dashboard_engine.models import Music
from dashboard_engine.sources.base import MAX_BACKOFF_FACTOR, DisabledSource, Source
from dashboard_engine.sources.minecraft import build_minecraft_source, clean_motd, query_server
from dashboard_engine.sources.music import build_music_source
from dashboard_engine.sources.obs import ObsClient, compute_auth
from dashboard_engine.sources.stream import (
    build_broadcaster_client,
    build_stream_source,
    parse_started_at,
)
from dashboard_engine.sources.streamlabs_desktop import StreamlabsDesktopClient
from dashboard_engine.sources.weather import build_weather_source, parse_current, parse_forecast

# --- socle ---------------------------------------------------------------


class _Flaky(Source[Music]):
    name = "flaky"

    def __init__(self, fail: bool) -> None:
        super().__init__(1.0, Music())
        self.fail = fail
        self.calls = 0

    async def fetch(self) -> Music:
        self.calls += 1
        if self.fail:
            raise RuntimeError("boum")
        return Music(title="Ok")


async def test_refresh_marks_available() -> None:
    source = _Flaky(fail=False)
    await source.refresh()
    assert source.payload.available is True
    assert source.payload.error is None
    assert source.payload.updated_at == pytest.approx(time.time(), abs=5)


async def test_failure_keeps_previous_payload() -> None:
    source = _Flaky(fail=False)
    await source.refresh()
    source.fail = True
    await source.refresh()
    # La derniere valeur connue reste affichee, annotee d'une erreur.
    assert source.payload.title == "Ok"
    assert source.payload.error == "RuntimeError: boum"


async def test_backoff_grows_then_caps() -> None:
    source = _Flaky(fail=True)
    assert source._next_delay == 1.0
    for _ in range(10):
        await source.refresh()
    assert source._next_delay == MAX_BACKOFF_FACTOR * source.interval_s


async def test_backoff_resets_after_success() -> None:
    source = _Flaky(fail=True)
    await source.refresh()
    source.fail = False
    await source.refresh()
    assert source._next_delay == source.interval_s


def test_disabled_source_never_starts() -> None:
    source: DisabledSource = DisabledSource("music", Music(), "desactive")
    source.start()
    assert source._task is None
    assert source.name == "music"
    assert source.payload.error == "desactive"
    assert source.payload.available is False


# --- fabriques -----------------------------------------------------------


def test_disabled_modules_return_disabled_sources() -> None:
    assert isinstance(build_music_source(MusicConfig(enabled=False)), DisabledSource)
    assert isinstance(build_minecraft_source(MinecraftConfig(enabled=False)), DisabledSource)
    assert isinstance(build_weather_source(WeatherConfig(enabled=False)), DisabledSource)
    assert isinstance(build_stream_source(StreamConfig(enabled=False)), DisabledSource)


def test_weather_without_api_key_is_disabled() -> None:
    source = build_weather_source(WeatherConfig(enabled=True, api_key=""))
    assert isinstance(source, DisabledSource)
    assert "cle API" in (source.payload.error or "")


def test_minecraft_without_servers_is_disabled() -> None:
    source = build_minecraft_source(MinecraftConfig(enabled=True, servers=[]))
    assert isinstance(source, DisabledSource)


def test_stream_without_twitch_still_runs_for_a_broadcaster() -> None:
    """Sans Twitch, l'onglet garde son interet : l'etat local du logiciel."""
    for kind in ("obs", "streamlabs"):
        config = StreamConfig(enabled=True)
        config.broadcaster.kind = kind
        assert not isinstance(build_stream_source(config), DisabledSource), kind


def test_stream_without_twitch_nor_broadcaster_is_disabled() -> None:
    config = StreamConfig(enabled=True)
    config.broadcaster.kind = "none"
    assert isinstance(build_stream_source(config), DisabledSource)


def test_broadcaster_client_follows_the_configured_kind() -> None:
    assert isinstance(build_broadcaster_client(BroadcasterConfig(kind="obs")), ObsClient)
    assert isinstance(
        build_broadcaster_client(BroadcasterConfig(kind="streamlabs")), StreamlabsDesktopClient
    )
    assert build_broadcaster_client(BroadcasterConfig(kind="none")) is None


# --- Minecraft -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("§aServeur §lSurvie", "Serveur Survie"),
        ("Ligne 1\nLigne 2", "Ligne 1 Ligne 2"),
        ("  espaces   multiples  ", "espaces multiples"),
        ("", ""),
    ],
)
def test_clean_motd(raw: str, expected: str) -> None:
    assert clean_motd(raw) == expected


def test_clean_motd_truncates() -> None:
    result = clean_motd("a" * 200)
    assert len(result) == 80
    assert result.endswith("…")


async def test_unreachable_server_is_reported_offline() -> None:
    # `.invalid` est un TLD reserve : la resolution echoue sans sortir du reseau.
    entry = MinecraftServerConfig(name="Test", host="serveur.invalid")
    result = await query_server(entry, timeout_s=1.0)
    assert result.online is False
    assert result.name == "Test"
    assert result.error


# --- meteo ---------------------------------------------------------------

OWM_CURRENT = {
    "name": "Paris",
    "main": {"temp": 18.24, "feels_like": 17.4, "temp_min": 16.0, "temp_max": 20.0, "humidity": 62},
    "wind": {"speed": 3.2},
    "sys": {"sunrise": 1725, "sunset": 1760},
    "weather": [{"description": "ciel degage", "icon": "01d"}],
}


def test_parse_current() -> None:
    weather = parse_current(OWM_CURRENT)
    assert weather.city == "Paris"
    assert weather.temp_c == pytest.approx(18.24)
    assert weather.description == "Ciel degage"
    assert weather.icon == "01d"
    assert weather.wind_kph == pytest.approx(11.5)  # 3.2 m/s -> km/h


def test_parse_current_tolerates_missing_blocks() -> None:
    weather = parse_current({})
    assert weather.city == ""
    assert weather.temp_c == 0.0
    assert weather.icon == ""


def test_parse_forecast_respects_limit() -> None:
    payload = {
        "list": [
            {"dt": i, "main": {"temp": 10.0 + i}, "weather": [{"icon": "02d"}]} for i in range(10)
        ]
    }
    points = parse_forecast(payload, 3)
    assert len(points) == 3
    assert points[0].ts == 0
    assert points[2].temp_c == pytest.approx(12.0)


def test_parse_forecast_empty() -> None:
    assert parse_forecast({}, 6) == []


# --- OBS -----------------------------------------------------------------


def test_compute_auth_follows_the_documented_formula() -> None:
    """Verifie l'ordre de composition impose par obs-websocket v5.

    L'erreur classique est d'inverser `salt` et `challenge`, ou de hasher les
    octets bruts au lieu de la chaine base64 intermediaire. On recalcule donc la
    valeur attendue independamment, directement depuis la formule du protocole :
    base64(sha256(base64(sha256(password + salt)) + challenge)).
    """
    password, salt, challenge = "supersecretpassword", "sel-de-test", "defi-de-test"
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    expected = base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()

    assert compute_auth(password, salt, challenge) == expected
    # Intervertir les deux composants doit changer le resultat.
    assert compute_auth(password, challenge, salt) != expected


def test_compute_auth_is_deterministic() -> None:
    assert compute_auth("a", "b", "c") == compute_auth("a", "b", "c")
    assert compute_auth("a", "b", "c") != compute_auth("z", "b", "c")


# --- Twitch --------------------------------------------------------------


def test_parse_started_at() -> None:
    recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    assert parse_started_at(recent) == pytest.approx(3600, abs=5)


def test_parse_started_at_invalid_returns_zero() -> None:
    assert parse_started_at("") == 0
    assert parse_started_at("hier soir") == 0
