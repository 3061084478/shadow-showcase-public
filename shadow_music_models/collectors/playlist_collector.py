from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..config_store import ConfigStore
from ..netease_api import NeteaseApiClient
from ..preprocessing import normalize_publish_time


class PlaylistCollector:
    def __init__(self, api_client: NeteaseApiClient, config_store: ConfigStore):
        self.api_client = api_client
        self.config_store = config_store
        self._album_cache: Dict[str, Dict[str, Any]] = {}
        self._album_workers = 8

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _write_jsonl(self, path: Path, rows: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _collect_album_details(self, album_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        albums: Dict[str, Dict[str, Any]] = {}
        uncached_album_ids: list[str] = []
        for album_id in sorted({str(value).strip() for value in album_ids if str(value).strip()}):
            cached = self._album_cache.get(album_id)
            if cached is not None:
                albums[album_id] = cached
                continue
            uncached_album_ids.append(album_id)

        if not uncached_album_ids:
            return albums

        if len(uncached_album_ids) == 1:
            album_id = uncached_album_ids[0]
            try:
                album_payload = self.api_client.get_album_detail(album_id)
            except Exception:
                album_payload = {}
            albums[album_id] = album_payload
            self._album_cache[album_id] = album_payload
            return albums

        worker_count = min(self._album_workers, len(uncached_album_ids))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_album_id = {
                executor.submit(self.api_client.clone().get_album_detail, album_id): album_id
                for album_id in uncached_album_ids
            }
            for future in as_completed(future_to_album_id):
                album_id = future_to_album_id[future]
                try:
                    album_payload = future.result()
                except Exception:
                    album_payload = {}
                albums[album_id] = album_payload
                self._album_cache[album_id] = album_payload
        return albums

    def _collect_all_playlist_tracks(self, playlist_id: str, expected_count: int) -> Dict[str, Any]:
        page_size = 1000
        offset = 0
        merged_songs: List[Dict[str, Any]] = []
        seen_song_ids: set[str] = set()
        last_page: Dict[str, Any] = {"songs": [], "code": 200}

        while True:
            page = self.api_client.get_playlist_tracks(playlist_id, limit=page_size, offset=offset)
            last_page = page
            songs = page.get("songs") or []
            if not songs:
                break

            new_count = 0
            for song in songs:
                song_id = str(song.get("id") or "").strip()
                dedupe_key = song_id or f"offset:{offset}:index:{len(merged_songs)}"
                if dedupe_key in seen_song_ids:
                    continue
                seen_song_ids.add(dedupe_key)
                merged_songs.append(song)
                new_count += 1

            if len(songs) < page_size:
                break
            if expected_count > 0 and len(merged_songs) >= expected_count:
                break
            if new_count == 0:
                break
            offset += page_size

        merged_payload = dict(last_page)
        merged_payload["songs"] = merged_songs
        return merged_payload

    def collect_playlist(self, playlist_id: str) -> Dict[str, Any]:
        playlist_id = str(playlist_id or "").strip()
        if not playlist_id:
            raise ValueError("playlist_id 不能为空")

        detail_data = self.api_client.get_playlist_detail(playlist_id)
        playlist = detail_data.get("playlist") or {}
        expected_track_count = int(playlist.get("trackCount") or 0)
        track_data = self._collect_all_playlist_tracks(playlist_id, expected_track_count)

        raw_playlist_dir = self.config_store.raw_data_dir / "playlists"
        self._write_json(raw_playlist_dir / f"{playlist_id}_detail.json", detail_data)
        self._write_json(raw_playlist_dir / f"{playlist_id}_tracks.json", track_data)

        tracks = track_data.get("songs") or []
        album_ids = [
            str((track.get("al") or {}).get("id") or "").strip()
            for track in tracks
        ]
        album_details = self._collect_album_details(album_ids)

        self._write_json(raw_playlist_dir / f"{playlist_id}_albums.json", album_details)

        standardized_rows: List[Dict[str, Any]] = []
        missing_publish_time = 0

        for track in tracks:
            song_id = str(track.get("id") or "").strip()
            album_data = track.get("al") or {}
            album_id = str(album_data.get("id") or "").strip()
            album_detail = (album_details.get(album_id) or {}).get("album") or {}
            publish_time = normalize_publish_time(
                album_detail.get("publishTime") or album_data.get("publishTime") or ""
            )

            quality_flags: List[str] = []
            if not publish_time:
                missing_publish_time += 1
                quality_flags.append("missing_album_publish_time")
            if album_id and not album_detail:
                quality_flags.append("missing_album_detail")
            album_name = str(album_detail.get("name") or album_data.get("name") or "").strip()
            if not album_name:
                quality_flags.append("missing_album_name")
            if not str(track.get("name") or "").strip():
                quality_flags.append("missing_song_name")
            if not any(str(artist.get("name") or "").strip() for artist in (track.get("ar") or [])):
                quality_flags.append("missing_artist_names")

            row = {
                "song_id": song_id,
                "song_name": str(track.get("name") or "").strip(),
                "artist_names": [
                    str(artist.get("name") or "").strip()
                    for artist in (track.get("ar") or [])
                    if str(artist.get("name") or "").strip()
                ],
                "album_name": album_name,
                "album_publish_time": publish_time,
                "source_playlist_id": playlist_id,
                "data_quality_flags": quality_flags,
            }
            standardized_rows.append(row)

        processed_path = self.config_store.processed_data_dir / f"playlist_{playlist_id}_songs.jsonl"
        report_path = self.config_store.output_data_dir / f"playlist_{playlist_id}_collection_report.json"
        self._write_jsonl(processed_path, standardized_rows)

        report = {
            "playlist_id": playlist_id,
            "playlist_name": str(playlist.get("name") or "").strip(),
            "song_count": len(standardized_rows),
            "missing_album_publish_time_count": missing_publish_time,
            "raw_paths": {
                "detail": str(raw_playlist_dir / f"{playlist_id}_detail.json"),
                "tracks": str(raw_playlist_dir / f"{playlist_id}_tracks.json"),
                "albums": str(raw_playlist_dir / f"{playlist_id}_albums.json"),
            },
            "processed_path": str(processed_path),
        }
        self._write_json(report_path, report)

        return {
            "playlist_id": playlist_id,
            "playlist_name": str(playlist.get("name") or "").strip(),
            "playlist_description": str(playlist.get("description") or "").strip(),
            "songs": standardized_rows,
            "report": report,
            "report_path": str(report_path),
        }

    def collect_playlists(self, playlist_ids: Iterable[str]) -> List[Dict[str, Any]]:
        return [self.collect_playlist(playlist_id) for playlist_id in playlist_ids if str(playlist_id).strip()]
