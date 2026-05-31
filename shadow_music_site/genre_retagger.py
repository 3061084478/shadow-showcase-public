from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config_store import ConfigStore
from .song_tagger import SongTagger
from .storage import SiteRepository


class GenreRetaggerService:
    def __init__(self, repository: SiteRepository, song_tagger: SongTagger, config_store: ConfigStore) -> None:
        self.repository = repository
        self.song_tagger = song_tagger
        self.config_store = config_store
        self.state_path = self.config_store.output_dir / "genre_reindex_state.json"

    def _default_state(self) -> Dict[str, Any]:
        return {
            "mapping_sha256": "",
            "base_version": 0,
            "applied_delta_version": 0,
            "last_reindexed_at": "",
            "last_result_summary": {},
        }

    def load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        merged = self._default_state()
        merged.update(payload)
        return merged

    def _save_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._default_state()
        merged.update(payload)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def _retag_song_fact(self, song_fact: Dict[str, Any]) -> Dict[str, Any]:
        base_payload = {
            "song_id": str(song_fact.get("song_id") or "").strip(),
            "song_name": str(song_fact.get("song_name") or "").strip(),
            "artist_names": list(song_fact.get("artist_names") or []),
            "album_id": str(song_fact.get("album_id") or "").strip(),
            "album_name": str(song_fact.get("album_name") or "").strip(),
            "publish_time": str(song_fact.get("publish_time") or "").strip(),
        }
        tag_result = self.song_tagger.predict(base_payload)
        updated_fact = dict(base_payload)
        updated_fact.update(
            {
                "genre_label": str(tag_result.get("genre_label") or "未知").strip() or "未知",
                "genre_status": str(tag_result.get("genre_status") or "unknown").strip() or "unknown",
                "genre_backend": str(tag_result.get("genre_backend") or "").strip(),
            }
        )
        self.repository.upsert_song_fact(updated_fact)
        updated_message_rows = self.repository.sync_song_fact_to_shared_messages(updated_fact)
        removed_unknown_rows = 0
        removed_pending_upload_rows = 0
        if updated_fact["genre_status"] == "known":
            removed_unknown_rows = self.repository.remove_unknown_by_song(updated_fact["song_id"])
            updated_message_rows += self.repository.sync_shared_song_messages_by_metadata(updated_fact)
            removed_unknown_rows += self.repository.remove_unknown_by_song_metadata(updated_fact)
            removed_pending_upload_rows = self.repository.remove_pending_unknown_upload_by_song_fact(updated_fact)
        return {
            "song_id": updated_fact["song_id"],
            "genre_status": updated_fact["genre_status"],
            "updated_message_rows": updated_message_rows,
            "removed_unknown_rows": removed_unknown_rows,
            "removed_pending_upload_rows": removed_pending_upload_rows,
        }

    def _retag_orphan_unknown_messages(self) -> Dict[str, Any]:
        rows = self.repository.list_distinct_unknown_song_candidates()
        total_checked = 0
        retagged_to_known = 0
        updated_message_rows = 0
        removed_pending_upload_rows = 0
        checked_song_ids: List[str] = []
        for row in rows:
            song_fact = {
                "song_id": str(row.get("song_id") or "").strip(),
                "song_name": str(row.get("song_name") or "").strip(),
                "artist_names": list(row.get("artist_names") or []),
                "album_id": str(row.get("album_id") or "").strip(),
                "album_name": str(row.get("album_name") or "").strip(),
                "publish_time": str(row.get("publish_time") or "").strip(),
            }
            total_checked += 1
            result = self._retag_song_fact(song_fact)
            checked_song_ids.append(result["song_id"] or song_fact["song_name"])
            updated_message_rows += int(result.get("updated_message_rows") or 0)
            removed_pending_upload_rows += int(result.get("removed_pending_upload_rows") or 0)
            if result["genre_status"] == "known":
                retagged_to_known += 1
        return {
            "total_checked": total_checked,
            "retagged_to_known": retagged_to_known,
            "updated_message_rows": updated_message_rows,
            "removed_pending_upload_rows": removed_pending_upload_rows,
            "checked_song_ids": checked_song_ids,
        }

    def reindex_unknown(self) -> Dict[str, Any]:
        unknown_facts = self.repository.list_song_facts(genre_status="unknown")
        total_checked = len(unknown_facts)
        retagged_to_known = 0
        still_unknown = 0
        updated_message_rows = 0
        removed_pending_upload_rows = 0
        checked_song_ids: List[str] = []
        for song_fact in unknown_facts:
            result = self._retag_song_fact(song_fact)
            checked_song_ids.append(result["song_id"])
            updated_message_rows += int(result.get("updated_message_rows") or 0)
            removed_pending_upload_rows += int(result.get("removed_pending_upload_rows") or 0)
            if result["genre_status"] == "known":
                retagged_to_known += 1
            else:
                still_unknown += 1
        orphan_result = self._retag_orphan_unknown_messages()
        return {
            "mode": "unknown_only",
            "total_checked": total_checked + int(orphan_result.get("total_checked") or 0),
            "retagged_to_known": retagged_to_known + int(orphan_result.get("retagged_to_known") or 0),
            "still_unknown": still_unknown,
            "updated_message_rows": updated_message_rows + int(orphan_result.get("updated_message_rows") or 0),
            "removed_pending_upload_rows": removed_pending_upload_rows + int(orphan_result.get("removed_pending_upload_rows") or 0),
            "checked_song_ids": checked_song_ids + list(orphan_result.get("checked_song_ids") or []),
        }

    def reindex_all(self) -> Dict[str, Any]:
        song_facts = self.repository.list_song_facts()
        total_checked = len(song_facts)
        retagged_to_known = 0
        still_unknown = 0
        updated_message_rows = 0
        removed_pending_upload_rows = 0
        checked_song_ids: List[str] = []
        for song_fact in song_facts:
            result = self._retag_song_fact(song_fact)
            checked_song_ids.append(result["song_id"])
            updated_message_rows += int(result.get("updated_message_rows") or 0)
            removed_pending_upload_rows += int(result.get("removed_pending_upload_rows") or 0)
            if result["genre_status"] == "known":
                retagged_to_known += 1
            else:
                still_unknown += 1
        orphan_result = self._retag_orphan_unknown_messages()
        return {
            "mode": "all_manual",
            "total_checked": total_checked + int(orphan_result.get("total_checked") or 0),
            "retagged_to_known": retagged_to_known + int(orphan_result.get("retagged_to_known") or 0),
            "still_unknown": still_unknown,
            "updated_message_rows": updated_message_rows + int(orphan_result.get("updated_message_rows") or 0),
            "removed_pending_upload_rows": removed_pending_upload_rows + int(orphan_result.get("removed_pending_upload_rows") or 0),
            "checked_song_ids": checked_song_ids + list(orphan_result.get("checked_song_ids") or []),
        }

    def auto_reindex_for_mapping(self, mapping_status: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
        mapping_sha = str(mapping_status.get("local_mapping_sha256") or "").strip()
        if not mapping_sha:
            return {
                "triggered": False,
                "reason": "mapping_sha_missing",
                "state": self.load_state(),
            }

        base_version = int(mapping_status.get("base_version") or 0)
        applied_delta_version = int(mapping_status.get("applied_delta_version") or 0)
        current_state = self.load_state()
        if (
            not force
            and str(current_state.get("mapping_sha256") or "").strip() == mapping_sha
            and int(current_state.get("base_version") or 0) == base_version
            and int(current_state.get("applied_delta_version") or 0) == applied_delta_version
        ):
            return {
                "triggered": False,
                "reason": "mapping_already_reindexed",
                "state": current_state,
            }

        summary = self.reindex_all()
        next_state = self._save_state(
            {
                "mapping_sha256": mapping_sha,
                "base_version": base_version,
                "applied_delta_version": applied_delta_version,
                "last_reindexed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_result_summary": summary,
            }
        )
        return {
            "triggered": True,
            "reason": "mapping_changed",
            "state": next_state,
            "summary": summary,
        }
