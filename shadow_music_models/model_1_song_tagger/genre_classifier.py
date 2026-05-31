from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

DEFAULT_GENRE_BACKEND = "mapping_exact_v1"

LABEL_SPLIT_RE = re.compile(r"[,/|;；、]+")


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


class GenreClassifier:
    def __init__(self, allowed_tags: Iterable[str], artifact_path: Path | None = None) -> None:
        self.allowed_tags = {str(tag).strip() for tag in allowed_tags if str(tag).strip()}
        self.mapping_path = Path(artifact_path) if artifact_path else None
        self.mapping_bundle: Dict[str, Any] | None = None
        self.load_error = ""
        self.backend_name = "mapping_unavailable_v1"
        if self.mapping_path and self.mapping_path.exists():
            self._load_mapping_bundle()

    @staticmethod
    def required_training_fields() -> List[str]:
        return [
            "artist_names",
            "album_name",
            "song_name",
            "genre_label",
        ]

    @staticmethod
    def normalize_genre_labels(raw_value: Any) -> List[str]:
        if isinstance(raw_value, list):
            values = raw_value
        elif isinstance(raw_value, tuple):
            values = list(raw_value)
        elif isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return []
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    values = parsed if isinstance(parsed, list) else [text]
                except json.JSONDecodeError:
                    values = LABEL_SPLIT_RE.split(text)
            else:
                values = LABEL_SPLIT_RE.split(text)
        else:
            return []

        labels: List[str] = []
        seen: set[str] = set()
        for value in values:
            label = str(value or "").strip()
            if not label or label in seen:
                continue
            labels.append(label)
            seen.add(label)
        return labels

    @classmethod
    def primary_genre_label(cls, raw_value: Any) -> str:
        labels = cls.normalize_genre_labels(raw_value)
        return labels[0] if labels else ""

    @staticmethod
    def _normalize_artist_names(values: Iterable[Any]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for value in values:
            artist = str(value or "").strip()
            if not artist:
                continue
            key = artist.lower()
            if key in seen:
                continue
            normalized.append(artist)
            seen.add(key)
        return normalized

    @staticmethod
    def _normalize_key_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).lower()

    @classmethod
    def build_artist_key(cls, artist_names: Iterable[Any]) -> str:
        artists = cls._normalize_artist_names(artist_names)
        return "|".join(sorted(artist.lower() for artist in artists))

    @classmethod
    def build_artist_album_key(cls, artist_names: Iterable[Any], album_name: Any) -> str:
        artist_key = cls.build_artist_key(artist_names)
        album_key = cls._normalize_key_text(album_name)
        return f"{artist_key}::{album_key}" if artist_key or album_key else ""

    @classmethod
    def build_artist_song_key(cls, artist_names: Iterable[Any], song_name: Any) -> str:
        artist_key = cls.build_artist_key(artist_names)
        song_key = cls._normalize_key_text(song_name)
        return f"{artist_key}::{song_key}" if artist_key or song_key else ""

    @staticmethod
    def build_feature_text(song_data: Dict[str, Any]) -> str:
        artists = " ".join(str(item).strip() for item in (song_data.get("artist_names") or []) if str(item).strip())
        album_name = str(song_data.get("album_name") or "").strip()
        song_name = str(song_data.get("song_name") or "").strip()
        return " [SEP] ".join(
            part
            for part in [
                artists,
                album_name,
                song_name,
            ]
            if part
        )

    def _load_mapping_bundle(self) -> None:
        try:
            with self.mapping_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if not isinstance(payload, dict):
                raise ValueError("映射文件必须是 JSON 对象。")
            self.mapping_bundle = payload
            self.backend_name = str(self.mapping_bundle.get("model_version") or DEFAULT_GENRE_BACKEND)
        except Exception as exc:  # pragma: no cover
            self.mapping_bundle = None
            self.load_error = str(exc)
            self.backend_name = "mapping_unavailable_v1"

    @staticmethod
    def _format_candidates(candidates: List[Tuple[str, float]], top_k: int = 3) -> List[Dict[str, Any]]:
        if not candidates:
            return [{"tag": "未知", "confidence": 0.4}]
        return [{"tag": tag, "confidence": round(confidence, 2)} for tag, confidence in candidates[:top_k]]

    @staticmethod
    def _serialize_counter_map(counter_map: Dict[str, Counter[str]]) -> Dict[str, Dict[str, int]]:
        serialized: Dict[str, Dict[str, int]] = {}
        for key, counter in counter_map.items():
            if not counter:
                continue
            serialized[key] = {label: int(count) for label, count in counter.items() if int(count) > 0}
        return serialized

    def _counter_to_candidates(self, counter_map: Dict[str, Any]) -> List[Tuple[str, float]]:
        scores: List[Tuple[str, float]] = []
        total = 0.0
        for label, value in counter_map.items():
            tag = str(label).strip()
            if tag not in self.allowed_tags or tag == "未知":
                continue
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if score <= 0:
                continue
            scores.append((tag, score))
            total += score
        if total <= 0:
            return []
        return sorted(((tag, score / total) for tag, score in scores), key=lambda item: (-item[1], item[0]))

    def _mapping_lookup(self, source_key: str, key: str) -> List[Tuple[str, float]]:
        if not self.mapping_bundle or not key:
            return []
        raw_counter = self.mapping_bundle.get(source_key) or {}
        if not isinstance(raw_counter, dict):
            return []
        value = raw_counter.get(key) or {}
        if not isinstance(value, dict):
            return []
        return self._counter_to_candidates(value)

    def _merge_candidate_lists(self, candidate_lists: Iterable[List[Tuple[str, float]]]) -> List[Tuple[str, float]]:
        merged_scores: Dict[str, float] = defaultdict(float)
        for candidates in candidate_lists:
            for tag, score in candidates:
                merged_scores[str(tag).strip()] += float(score)
        return self._counter_to_candidates(merged_scores)

    def _predict_from_individual_artists(self, artist_names: Iterable[Any]) -> Dict[str, Any]:
        normalized_artists = self._normalize_artist_names(artist_names)
        if not normalized_artists:
            return {}

        candidate_lists: List[List[Tuple[str, float]]] = []
        matched_artists: List[str] = []
        for artist in normalized_artists:
            artist_key = self._normalize_key_text(artist)
            candidates = self._mapping_lookup("artist_label_counter", artist_key)
            if not candidates:
                continue
            candidate_lists.append(candidates)
            matched_artists.append(artist)

        if not candidate_lists:
            return {}

        merged_candidates = self._merge_candidate_lists(candidate_lists)
        if not merged_candidates:
            return {}

        return {
            "candidates": merged_candidates,
            "mapping_source": "artist_individual_vote",
            "matched_key": "|".join(sorted(name.lower() for name in matched_artists)),
            "matched_artists": matched_artists,
            "prediction_mode": "artist_individual_vote",
        }

    def _predict_with_mapping(self, song_data: Dict[str, Any]) -> Dict[str, Any]:
        artist_names = song_data.get("artist_names") or []
        album_name = str(song_data.get("album_name") or "").strip()
        song_name = str(song_data.get("song_name") or "").strip()

        lookup_order = [
            ("artist", self.build_artist_key(artist_names), "artist_label_counter"),
            ("artist_album", self.build_artist_album_key(artist_names, album_name), "artist_album_label_counter"),
            ("artist_song", self.build_artist_song_key(artist_names, song_name), "artist_song_label_counter"),
        ]
        for source_name, key, source_key in lookup_order:
            candidates = self._mapping_lookup(source_key, key)
            if candidates:
                return {
                    "candidates": candidates,
                    "mapping_source": source_name,
                    "matched_key": key,
                    "prediction_mode": "mapping_exact_match",
                }

        return self._predict_from_individual_artists(artist_names)

    def predict(self, song_data: Dict[str, Any]) -> Dict[str, Any]:
        model_payload = self._predict_with_mapping(song_data)
        if model_payload:
            return {
                "genre_tags": self._format_candidates(model_payload.get("candidates") or []),
                "genre_backend": self.backend_name,
                "genre_evidence": {
                    "feature_text": self.build_feature_text(song_data)[:240],
                    "mapping_path": str(self.mapping_path) if self.mapping_path else "",
                    "prediction_mode": model_payload.get("prediction_mode") or "mapping_exact_match",
                    "mapping_source": model_payload.get("mapping_source") or "",
                    "matched_key": model_payload.get("matched_key") or "",
                },
            }
        return {
            "genre_tags": [{"tag": "未知", "confidence": 0.4}],
            "genre_backend": self.backend_name,
            "genre_evidence": {
                "feature_text": self.build_feature_text(song_data)[:240],
                "mapping_path": str(self.mapping_path) if self.mapping_path else "",
                "prediction_mode": "unknown_no_exact_match",
                "fallback_reason": self.load_error or "no_exact_mapping_match",
            },
        }

    @classmethod
    def train_and_save(
        cls,
        training_rows: Iterable[Dict[str, Any]],
        output_path: Path,
        allowed_tags: Iterable[str],
        artist_prior_weight: float | None = None,
    ) -> Path:
        del artist_prior_weight

        allowed = {str(tag).strip() for tag in allowed_tags if str(tag).strip() and str(tag).strip() != "未知"}
        artist_label_counter: Dict[str, Counter[str]] = defaultdict(Counter)
        artist_album_label_counter: Dict[str, Counter[str]] = defaultdict(Counter)
        artist_song_label_counter: Dict[str, Counter[str]] = defaultdict(Counter)
        accepted_rows = 0

        for row in training_rows:
            label = cls.primary_genre_label(row.get("genre_labels") or row.get("genre_label"))
            if not label:
                continue
            if label not in allowed:
                raise ValueError(f"训练样本包含非法主流派标签: {label}")

            song_name = str(row.get("song_name") or "").strip()
            album_name = str(row.get("album_name") or "").strip()
            artists = cls._normalize_artist_names(row.get("artist_names") or [])
            if not song_name or not artists:
                continue

            accepted_rows += 1
            for artist in artists:
                artist_label_counter[artist.lower()].update([label])

            artist_key = cls.build_artist_key(artists)
            if artist_key and album_name:
                artist_album_label_counter[cls.build_artist_album_key(artists, album_name)].update([label])
            if artist_key and song_name:
                artist_song_label_counter[cls.build_artist_song_key(artists, song_name)].update([label])

        if accepted_rows < 20:
            raise ValueError("训练样本太少，至少准备 20 条有效样本再构建映射。")

        artifact = {
            "model_version": "mapping_artist_album_song_v1",
            "allowed_tags": sorted(allowed),
            "training_size": accepted_rows,
            "artist_label_counter": cls._serialize_counter_map(artist_label_counter),
            "artist_album_label_counter": cls._serialize_counter_map(artist_album_label_counter),
            "artist_song_label_counter": cls._serialize_counter_map(artist_song_label_counter),
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
