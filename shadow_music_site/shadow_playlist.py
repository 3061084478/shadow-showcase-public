from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .sequence_builder import build_sequence

from .bootstrap import StartupBootstrap
from .config_store import ConfigStore
from .storage import SiteRepository


class ShadowPlaylistService:
    CANDIDATE_CURSOR_SCOPE = "shadow_candidate"

    def __init__(self, config_store: ConfigStore, bootstrap: StartupBootstrap, repository: SiteRepository) -> None:
        self.config_store = config_store
        self.bootstrap = bootstrap
        self.repository = repository

    @staticmethod
    def _build_candidate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        latest_by_song_id: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            song_id = str(row.get("song_id") or "").strip()
            if not song_id:
                continue
            latest_by_song_id[song_id] = {
                "song_id": song_id,
                "song_name": row.get("song_name") or "",
                "artist_names": row.get("artist_names") or [],
                "album_name": row.get("album_name") or "",
                "publish_time": row.get("publish_time") or "",
                "genre_label": row.get("genre_label") or "",
                "selected": False,
                "msg_id": str(row.get("msg_id") or ""),
                "msg_time_ms": int(row.get("msg_time_ms") or 0),
                "msg_time_str": str(row.get("msg_time_str") or ""),
            }
        return sorted(
            latest_by_song_id.values(),
            key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")),
        )

    def list_targets(self) -> Dict[str, Any]:
        account = self.bootstrap.ensure_authenticated()
        raw_playlists = self.bootstrap.api_client.get_user_playlists(account["user_id"])
        account_user_id = str(account.get("user_id") or "").strip()
        playlists = [
            playlist
            for playlist in raw_playlists
            if str((playlist.get("creator") or {}).get("userId") or playlist.get("userId") or "").strip() == account_user_id
        ]
        current = self.repository.get_shadow_playlist_target()
        current_tracks: List[Dict[str, Any]] = []
        playlist_id = str(current.get("playlist_id") or "").strip()
        if playlist_id:
            try:
                current_tracks = self.bootstrap.api_client.get_playlist_tracks(playlist_id)
            except Exception:
                current_tracks = []
        return {"current_target": current, "playlists": playlists, "current_tracks": current_tracks}

    def get_playlist_state(self) -> Dict[str, Any]:
        self.bootstrap.ensure_authenticated()
        target = self.repository.get_shadow_playlist_target()
        playlist_id = str(target.get("playlist_id") or "").strip()
        current_tracks: List[Dict[str, Any]] = []
        if playlist_id:
            try:
                current_tracks = self.bootstrap.api_client.get_playlist_tracks(playlist_id)
            except Exception:
                current_tracks = []
        return {
            "target": target,
            "current_tracks": current_tracks,
            "last_build": self.repository.get_last_shadow_playlist_build(),
        }

    def set_target(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        strategy = str(payload.get("strategy") or "use_existing").strip()
        playlist_id = str(payload.get("playlist_id") or "").strip()
        playlist_name = str(payload.get("playlist_name") or "").strip()
        is_private = bool(payload.get("is_private", False))

        if strategy == "auto_create":
            if not playlist_name:
                playlist_name = "Shadow Music Playlist"
            created = self.bootstrap.api_client.create_playlist(playlist_name, privacy=10 if is_private else 0)
            playlist_id = created["playlist_id"]
        elif not playlist_id:
            raise RuntimeError("未提供目标歌单 ID。")

        saved = {
            "playlist_id": playlist_id,
            "playlist_name": playlist_name,
            "strategy": strategy,
            "is_private": is_private,
            "last_set_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.repository.save_shadow_playlist_target(saved)
        self.config_store.update(
            shadow_playlist_id=playlist_id,
            shadow_playlist_name=playlist_name,
            shadow_playlist_strategy=strategy,
            shadow_playlist_private=is_private,
            shadow_playlist_last_set_at=saved["last_set_at"],
        )
        return saved

    def query_candidates(self, uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope = str(payload.get("scope") or "all").strip().lower()
        keyword = str(payload.get("keyword") or "").strip() or None
        known_only = bool(payload.get("known_only", True))
        date = str(payload.get("date") or "").strip()
        start_date = str(payload.get("start_date") or "").strip()
        end_date = str(payload.get("end_date") or "").strip()
        start_datetime = f"{date} 00:00:00" if date else (f"{start_date} 00:00:00" if start_date else None)
        end_datetime = f"{date} 23:59:59" if date else (f"{end_date} 23:59:59" if end_date else None)
        rows = self.repository.query_shared_song_messages(uid, keyword=keyword, known_only=known_only)
        if start_datetime:
            rows = [row for row in rows if str(row.get("msg_time_str") or "") >= start_datetime]
        if end_datetime:
            rows = [row for row in rows if str(row.get("msg_time_str") or "") <= end_datetime]
        deduped = self._build_candidate_rows(rows)
        raw_limit = payload.get("limit")
        has_explicit_limit = str(raw_limit or "").strip()
        limit = max(1, min(500, int(raw_limit or 50))) if has_explicit_limit else 50
        pages = max(1, int(payload.get("page") or 1))
        if scope == "incremental":
            state = self.repository.get_consumption_state(uid, self.CANDIDATE_CURSOR_SCOPE)
            start_ms = int((state or {}).get("last_consumed_msg_time_ms") or 0)
            start_msg_id = str((state or {}).get("last_consumed_msg_id") or "")
            deduped = [
                row
                for row in deduped
                if (int(row.get("msg_time_ms") or 0), str(row.get("msg_id") or "")) > (start_ms, start_msg_id)
            ]
        if scope == "recent":
            if limit > 0:
                deduped = deduped[-limit:]
        elif scope == "incremental":
            if limit > 0:
                deduped = deduped[-limit:]
        elif scope == "pages":
            deduped = deduped[-(pages * 30):]
        elif scope == "all" and has_explicit_limit and len(deduped) > limit:
            deduped = deduped[-limit:]
        return {"uid": uid, "scope": scope, "count": len(deduped), "rows": deduped}

    @staticmethod
    def _resolve_generation_sequence(
        song_messages: List[Dict[str, Any]],
        anchor_index: int,
        max_gap_hours: Optional[int],
        max_songs: Optional[int],
        apply_sequence_rules: bool,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], int, str]:
        if not song_messages:
            raise ValueError("没有解析到歌曲分享消息")
        if anchor_index < 0 or anchor_index >= len(song_messages):
            raise ValueError("起点编号越界")

        if apply_sequence_rules:
            return build_sequence(
                song_messages=song_messages,
                anchor_index=anchor_index,
                max_gap_hours=max_gap_hours,
                max_songs=max_songs,
            )

        anchor = song_messages[anchor_index]
        sequence = [item for item in song_messages[anchor_index:] if item.get("uid") == anchor.get("uid")]
        return anchor, sequence, 0, ""

    def build(self, uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        target = self.repository.get_shadow_playlist_target()
        playlist_id = str(payload.get("playlist_id") or target.get("playlist_id") or "").strip()
        if not playlist_id:
            raise RuntimeError("当前未设置目标歌单。")

        selected_song_ids = [str(item).strip() for item in (payload.get("song_ids") or []) if str(item).strip()]
        candidate_lookup = {
            row["song_id"]: row
            for row in self._build_candidate_rows(self.repository.query_shared_song_messages(uid, known_only=True))
        }
        if not selected_song_ids:
            candidates = self.query_candidates(uid, {"known_only": True, "scope": "all"})
            candidate_rows = candidates.get("rows") or []
            anchor_index = int(payload.get("anchor_index") or 0)
            max_gap_hours = payload.get("max_gap_hours")
            max_songs = payload.get("max_songs")
            apply_sequence_rules = bool(payload.get("apply_sequence_rules", True))
            anchor, sequence, skipped_duplicates, stop_reason = self._resolve_generation_sequence(
                song_messages=candidate_rows,
                anchor_index=anchor_index,
                max_gap_hours=int(max_gap_hours) if max_gap_hours is not None else None,
                max_songs=int(max_songs) if max_songs is not None else None,
                apply_sequence_rules=apply_sequence_rules,
            )
            selected_song_ids = [str(item.get("song_id") or "") for item in sequence if str(item.get("song_id") or "")]
        else:
            anchor = candidate_lookup.get(selected_song_ids[0], {"song_id": selected_song_ids[0], "song_name": selected_song_ids[0], "msg_time_str": ""})
            sequence = []
            skipped_duplicates = 0
            stop_reason = "手动选择"

        overwrite = bool(payload.get("overwrite", True))
        if overwrite:
            existing_rows = self.bootstrap.api_client.get_playlist_tracks(playlist_id)
            existing_ids = [str(item.get("id") or "").strip() for item in existing_rows if str(item.get("id") or "").strip()]
            self.bootstrap.api_client.remove_tracks_from_playlist(playlist_id, existing_ids)
        self.bootstrap.api_client.add_tracks_to_playlist(playlist_id, selected_song_ids)

        latest_selected = None
        selected_candidates = [candidate_lookup.get(song_id) for song_id in selected_song_ids if candidate_lookup.get(song_id)]
        if selected_candidates:
            latest_selected = max(
                selected_candidates,
                key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")),
            )
            self.repository.advance_consumption_state(
                uid=uid,
                feature_scope=self.CANDIDATE_CURSOR_SCOPE,
                last_consumed_msg_id=str(latest_selected.get("msg_id") or ""),
                last_consumed_msg_time_ms=int(latest_selected.get("msg_time_ms") or 0),
                last_consumed_msg_time_str=str(latest_selected.get("msg_time_str") or ""),
            )

        friend = self.repository.get_friend(uid) or {"nickname": uid}
        build_payload = {
            "uid": uid,
            "friend_name": friend.get("nickname") or uid,
            "playlist_name": str(payload.get("playlist_name") or target.get("playlist_name") or ""),
            "generated_count": len(selected_song_ids),
            "track_ids": selected_song_ids,
            "overwrite": overwrite,
            "anchor_song_id": str(anchor.get("song_id") or ""),
            "anchor_song_name": str(anchor.get("song_name") or ""),
            "anchor_time": str(anchor.get("msg_time_str") or latest_selected.get("msg_time_str") if latest_selected else ""),
            "skipped_duplicates": skipped_duplicates,
            "stop_reason": stop_reason,
        }
        self.repository.save_shadow_playlist_build(build_payload)
        return build_payload

    def get_last_build_record(self) -> Optional[Dict[str, Any]]:
        return self.repository.get_last_shadow_playlist_build()
