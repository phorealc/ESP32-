"""Checklist persistante, partagee entre le PC et l'ESP32.

Le fichier JSON est la source de verite : il survit au redemarrage du moteur.
Chaque modification incremente `rev`, ce qui permet a l'ESP32 de detecter un
changement fait cote PC sans comparer tous les elements.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from dashboard_engine.models import Checklist, ChecklistItem

log = logging.getLogger(__name__)


def new_id() -> str:
    return uuid.uuid4().hex[:8]


class ChecklistStore:
    """Acces synchronise au fichier de checklist.

    Les ecritures sont atomiques (fichier temporaire puis `replace`) pour qu'une
    coupure de courant ne laisse pas un JSON tronque.
    """

    def __init__(self, path: Path, default_items: list[str] | None = None) -> None:
        self.path = Path(path)
        self._defaults = default_items or []
        self._checklist = self._load()

    # --- persistance -----------------------------------------------------

    def _load(self) -> Checklist:
        if self.path.is_file():
            try:
                return Checklist.model_validate_json(self.path.read_text(encoding="utf-8"))
            except Exception as exc:
                log.warning("checklist illisible (%s), reconstruction depuis les defauts", exc)
        return self._from_defaults()

    def _from_defaults(self) -> Checklist:
        return Checklist(
            rev=1,
            items=[
                ChecklistItem(id=new_id(), label=label, order=index)
                for index, label in enumerate(self._defaults)
            ],
        )

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(self._checklist.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(self.path)

    def _commit(self) -> Checklist:
        self._checklist.rev += 1
        self._reindex()
        self._save()
        return self.state()

    def _reindex(self) -> None:
        for index, item in enumerate(self._checklist.items):
            item.order = index

    # --- lecture ---------------------------------------------------------

    def state(self) -> Checklist:
        """Copie du contenu courant (les appelants ne mutent pas l'etat interne)."""
        return self._checklist.model_copy(deep=True)

    def find(self, item_id: str) -> ChecklistItem | None:
        return next((item for item in self._checklist.items if item.id == item_id), None)

    # --- ecriture --------------------------------------------------------

    def set_done(self, item_id: str, done: bool) -> Checklist:
        item = self.find(item_id)
        if item is None:
            raise KeyError(item_id)
        if item.done == done:
            return self.state()  # pas de rev inutile sur un POST idempotent
        item.done = done
        return self._commit()

    def toggle(self, item_id: str) -> Checklist:
        item = self.find(item_id)
        if item is None:
            raise KeyError(item_id)
        item.done = not item.done
        return self._commit()

    def add(self, label: str) -> Checklist:
        label = label.strip()
        if not label:
            raise ValueError("libelle vide")
        self._checklist.items.append(
            ChecklistItem(id=new_id(), label=label, order=len(self._checklist.items))
        )
        return self._commit()

    def rename(self, item_id: str, label: str) -> Checklist:
        item = self.find(item_id)
        if item is None:
            raise KeyError(item_id)
        label = label.strip()
        if not label:
            raise ValueError("libelle vide")
        item.label = label
        return self._commit()

    def remove(self, item_id: str) -> Checklist:
        if self.find(item_id) is None:
            raise KeyError(item_id)
        self._checklist.items = [i for i in self._checklist.items if i.id != item_id]
        return self._commit()

    def uncheck_all(self) -> Checklist:
        """Remet la liste a zero (rituel de debut de stream)."""
        for item in self._checklist.items:
            item.done = False
        return self._commit()

    def reorder(self, ordered_ids: list[str]) -> Checklist:
        """Reordonne selon `ordered_ids` ; les ids absents gardent leur ordre relatif."""
        known = {item.id: item for item in self._checklist.items}
        unknown = [i for i in ordered_ids if i not in known]
        if unknown:
            raise KeyError(unknown[0])
        ordered = [known[i] for i in ordered_ids]
        ordered += [item for item in self._checklist.items if item.id not in set(ordered_ids)]
        self._checklist.items = ordered
        return self._commit()
