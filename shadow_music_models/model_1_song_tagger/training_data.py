from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .genre_classifier import GenreClassifier


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    path: Path
    priority: int


def load_json_rows(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"训练集必须是 JSON 数组: {path}")
    return [row for row in payload if isinstance(row, dict)]


def normalize_artist_names(values: Iterable[Any]) -> List[str]:
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


def normalize_training_row(row: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    genre_label = str(
        row.get("genre_label")
        or GenreClassifier.primary_genre_label(row.get("genre_labels"))
        or ""
    ).strip()
    return {
        "song_name": str(row.get("song_name") or "").strip(),
        "artist_names": normalize_artist_names(row.get("artist_names") or []),
        "album_name": str(row.get("album_name") or "").strip(),
        "genre_label": genre_label,
    }


def build_song_key(row: Dict[str, Any]) -> str:
    song_name = str(row.get("song_name") or "").strip().lower()
    artists = "|".join(
        sorted(str(artist or "").strip().lower() for artist in (row.get("artist_names") or []) if str(artist).strip())
    )
    return f"{artists}::{song_name}"


def build_artist_name_set(rows: Iterable[Dict[str, Any]]) -> set[str]:
    artist_names: set[str] = set()
    for row in rows:
        for artist in normalize_artist_names(row.get("artist_names") or []):
            artist_names.add(artist.lower())
    return artist_names


def merge_training_datasets(dataset_specs: Iterable[DatasetSpec]) -> Dict[str, Any]:
    merged_map: Dict[str, Dict[str, Any]] = {}
    source_stats: Dict[str, Dict[str, Any]] = {}
    label_counter: Counter[str] = Counter()
    duplicate_count = 0
    conflict_count = 0

    specs = sorted(dataset_specs, key=lambda item: item.priority)
    for spec in specs:
        rows = load_json_rows(spec.path)
        accepted = 0
        skipped_empty = 0
        for row in rows:
            normalized = normalize_training_row(row, spec.name)
            if not normalized["song_name"] or not normalized["artist_names"] or not normalized["genre_label"]:
                skipped_empty += 1
                continue
            song_key = build_song_key(normalized)
            existing = merged_map.get(song_key)
            if existing is not None:
                duplicate_count += 1
                if existing["genre_label"] != normalized["genre_label"]:
                    conflict_count += 1
                continue
            merged_map[song_key] = normalized
            accepted += 1

        source_stats[spec.name] = {
            "path": str(spec.path),
            "priority": spec.priority,
            "input_count": len(rows),
            "accepted_count": accepted,
            "skipped_empty_count": skipped_empty,
        }

    merged_rows = sorted(
        merged_map.values(),
        key=lambda item: (
            item["genre_label"],
            "|".join(item["artist_names"]).lower(),
            item["song_name"].lower(),
        ),
    )
    for row in merged_rows:
        label_counter.update([row["genre_label"]])

    return {
        "rows": merged_rows,
        "report": {
            "total_rows": len(merged_rows),
            "duplicate_count": duplicate_count,
            "conflict_count": conflict_count,
            "source_stats": source_stats,
            "genre_distribution": dict(sorted(label_counter.items(), key=lambda item: (item[0]))),
        },
    }
