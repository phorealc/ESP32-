from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard_engine.checklist import ChecklistStore


@pytest.fixture
def store(tmp_path: Path) -> ChecklistStore:
    return ChecklistStore(tmp_path / "checklist.json", ["Un", "Deux", "Trois"])


def test_defaults_are_seeded(store: ChecklistStore) -> None:
    state = store.state()
    assert [item.label for item in state.items] == ["Un", "Deux", "Trois"]
    assert [item.order for item in state.items] == [0, 1, 2]
    assert all(not item.done for item in state.items)


def test_toggle_flips_and_bumps_rev(store: ChecklistStore) -> None:
    before = store.state()
    item_id = before.items[0].id

    after = store.toggle(item_id)
    assert after.items[0].done is True
    assert after.rev == before.rev + 1

    assert store.toggle(item_id).items[0].done is False


def test_set_done_is_idempotent(store: ChecklistStore) -> None:
    item_id = store.state().items[0].id
    first = store.set_done(item_id, True)
    second = store.set_done(item_id, True)
    # Un ESP32 qui reemet le meme POST ne doit pas faire bouger `rev`, sinon la
    # coquille PC croit a un changement a chaque re-emission.
    assert second.rev == first.rev


def test_unknown_id_raises(store: ChecklistStore) -> None:
    with pytest.raises(KeyError):
        store.toggle("inconnu")
    with pytest.raises(KeyError):
        store.remove("inconnu")


def test_add_remove_and_reindex(store: ChecklistStore) -> None:
    state = store.add("Quatre")
    assert state.items[-1].label == "Quatre"

    state = store.remove(state.items[0].id)
    assert [item.label for item in state.items] == ["Deux", "Trois", "Quatre"]
    assert [item.order for item in state.items] == [0, 1, 2]


def test_add_rejects_blank_label(store: ChecklistStore) -> None:
    with pytest.raises(ValueError):
        store.add("   ")


def test_rename(store: ChecklistStore) -> None:
    item_id = store.state().items[1].id
    assert store.rename(item_id, "  Deux bis  ").items[1].label == "Deux bis"


def test_uncheck_all(store: ChecklistStore) -> None:
    for item in store.state().items:
        store.set_done(item.id, True)
    assert all(not item.done for item in store.uncheck_all().items)


def test_reorder(store: ChecklistStore) -> None:
    ids = [item.id for item in store.state().items]
    state = store.reorder([ids[2], ids[0]])
    # Les ids omis conservent leur ordre relatif, a la suite.
    assert [item.label for item in state.items] == ["Trois", "Un", "Deux"]
    assert [item.order for item in state.items] == [0, 1, 2]


def test_reorder_rejects_unknown_id(store: ChecklistStore) -> None:
    with pytest.raises(KeyError):
        store.reorder(["inconnu"])


def test_state_is_a_copy(store: ChecklistStore) -> None:
    state = store.state()
    state.items[0].label = "modifie a l'exterieur"
    assert store.state().items[0].label == "Un"


def test_persistence_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "checklist.json"
    first = ChecklistStore(path, ["Un", "Deux"])
    item_id = first.state().items[0].id
    first.toggle(item_id)

    second = ChecklistStore(path, ["Defauts", "Ignores"])
    reloaded = second.state()
    assert [item.label for item in reloaded.items] == ["Un", "Deux"]
    assert reloaded.items[0].done is True
    assert reloaded.items[0].id == item_id


def test_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "checklist.json"
    path.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    store = ChecklistStore(path, ["Secours"])
    assert [item.label for item in store.state().items] == ["Secours"]


def test_writes_are_valid_json(store: ChecklistStore) -> None:
    store.toggle(store.state().items[0].id)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["items"][0]["done"] is True
    # Le fichier temporaire d'ecriture atomique ne doit pas subsister.
    assert not store.path.with_suffix(".json.tmp").exists()
