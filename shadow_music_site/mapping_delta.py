from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

MAPPING_SECTION_KEYS = (
    "artist_label_counter",
    "artist_album_label_counter",
    "artist_song_label_counter",
)

TOP_LEVEL_METADATA_KEYS = (
    "model_version",
    "training_size",
    "allowed_tags",
)


def _utc_now_text() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def load_mapping_bundle(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("映射文件必须是 JSON 对象。")
    return payload


def save_mapping_bundle(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_mapping_sections(payload: Dict[str, Any]) -> Dict[str, Any]:
    for section_name in MAPPING_SECTION_KEYS:
        section_payload = payload.get(section_name)
        if not isinstance(section_payload, dict):
            payload[section_name] = {}
    return payload


def _section_updates(previous: Dict[str, Any], current: Dict[str, Any], section_name: str) -> Dict[str, Any]:
    previous_section = previous.get(section_name) if isinstance(previous.get(section_name), dict) else {}
    current_section = current.get(section_name) if isinstance(current.get(section_name), dict) else {}
    updates: Dict[str, Any] = {}
    for key, value in current_section.items():
        if previous_section.get(key) != value:
            updates[key] = deepcopy(value)
    return updates


def compute_mapping_delta(
    previous_bundle: Dict[str, Any],
    current_bundle: Dict[str, Any],
    *,
    base_version: int,
    delta_version: int,
    previous_delta_version: int,
    released_at: str | None = None,
) -> Dict[str, Any]:
    previous_bundle = ensure_mapping_sections(deepcopy(previous_bundle))
    current_bundle = ensure_mapping_sections(deepcopy(current_bundle))

    sections: Dict[str, Dict[str, Any]] = {}
    section_entry_counts: Dict[str, int] = {}
    total_entries = 0
    for section_name in MAPPING_SECTION_KEYS:
        updates = _section_updates(previous_bundle, current_bundle, section_name)
        if updates:
            sections[section_name] = updates
            section_entry_counts[section_name] = len(updates)
            total_entries += len(updates)

    bundle_updates: Dict[str, Any] = {}
    for key in TOP_LEVEL_METADATA_KEYS:
        if previous_bundle.get(key) != current_bundle.get(key):
            bundle_updates[key] = deepcopy(current_bundle.get(key))

    return {
        "base_version": int(base_version),
        "delta_version": int(delta_version),
        "previous_delta_version": int(previous_delta_version),
        "released_at": released_at or _utc_now_text(),
        "entry_count": total_entries,
        "section_entry_counts": section_entry_counts,
        "sections": sections,
        "bundle_updates": bundle_updates,
    }


def apply_mapping_delta(bundle: Dict[str, Any], delta_payload: Dict[str, Any]) -> Dict[str, Any]:
    bundle = ensure_mapping_sections(bundle)
    updated_bundle = deepcopy(bundle)

    sections = delta_payload.get("sections") or {}
    if not isinstance(sections, dict):
        raise ValueError("delta sections 必须是 JSON 对象。")

    for section_name, updates in sections.items():
        if section_name not in MAPPING_SECTION_KEYS:
            continue
        if not isinstance(updates, dict):
            raise ValueError(f"delta section {section_name} 必须是 JSON 对象。")
        target_section = updated_bundle.setdefault(section_name, {})
        if not isinstance(target_section, dict):
            target_section = {}
            updated_bundle[section_name] = target_section
        for key, value in updates.items():
            target_section[str(key)] = deepcopy(value)

    bundle_updates = delta_payload.get("bundle_updates") or {}
    if bundle_updates and not isinstance(bundle_updates, dict):
        raise ValueError("bundle_updates 必须是 JSON 对象。")
    for key, value in bundle_updates.items():
        updated_bundle[str(key)] = deepcopy(value)

    return updated_bundle
