from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..config_store import ConfigStore
from .genre_classifier import GenreClassifier


def _load_tag_pool(name: str) -> List[str]:
    config_path = Path(__file__).resolve().parents[1] / "config" / name
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


GENRE_TAGS = _load_tag_pool("genre_tags.json")


class SongTagger:
    def __init__(
        self,
        config_store: ConfigStore | None = None,
        genre_classifier: GenreClassifier | None = None,
    ) -> None:
        self.config_store = config_store or ConfigStore()
        config = self.config_store.load()
        self.genre_tags = set(GENRE_TAGS)

        mapping_path = None
        mapping_value = str(config.get("genre_mapping_path") or "").strip()
        if mapping_value:
            mapping_path = self.config_store.resolve_workspace_path(mapping_value)

        self.genre_classifier = genre_classifier or GenreClassifier(
            allowed_tags=self.genre_tags,
            artifact_path=mapping_path,
        )

    @staticmethod
    def _top_tag(tag_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not tag_rows:
            return {"tag": "未知", "confidence": 0.0}
        return tag_rows[0]

    def predict(self, song_data: Dict[str, Any]) -> Dict[str, Any]:
        genre_payload = self.genre_classifier.predict(song_data)
        top_genre = self._top_tag(genre_payload.get("genre_tags") or [])

        need_manual_check = (
            float(top_genre.get("confidence") or 0.0) < 0.6
            or str(top_genre.get("tag") or "") == "未知"
        )

        return {
            "song_id": str(song_data.get("song_id") or "").strip(),
            "genre_tags": genre_payload.get("genre_tags") or [{"tag": "未知", "confidence": 0.4}],
            "need_manual_check": need_manual_check,
            "genre_backend": genre_payload.get("genre_backend") or "mapping_unavailable_v1",
            "genre_evidence": genre_payload.get("genre_evidence") or {},
            "model_version": "song_tagger_v4_mapping_only",
        }

    def predict_many(self, songs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.predict(song) for song in songs]
