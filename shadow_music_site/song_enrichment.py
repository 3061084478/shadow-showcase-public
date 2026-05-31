from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

from .netease_api import NeteaseApiClient
from .preprocessing import normalize_publish_time
from .song_tagger import SongTagger
from .storage import SiteRepository


class SongEnrichmentService:
    def __init__(
        self,
        api_client: NeteaseApiClient,
        repository: SiteRepository,
        song_tagger: SongTagger,
    ) -> None:
        self.api_client = api_client
        self.repository = repository
        self.song_tagger = song_tagger

    @staticmethod
    def _chunked(values: List[str], size: int) -> Iterable[List[str]]:
        for index in range(0, len(values), size):
            yield values[index : index + size]

    @staticmethod
    def _normalize_artist_names(values: Iterable[Any]) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        for value in values:
            artist = str(value or "").strip()
            if not artist:
                continue
            key = artist.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(artist)
        return result

    @staticmethod
    def _resolve_album_publish_time(song_row: Dict[str, Any], album_row: Dict[str, Any]) -> str:
        for candidate in (
            song_row.get("publishTime"),
            song_row.get("publish_time"),
            song_row.get("album", {}).get("publishTime") if isinstance(song_row.get("album"), dict) else None,
            song_row.get("al", {}).get("publishTime") if isinstance(song_row.get("al"), dict) else None,
            album_row.get("album", {}).get("publishTime") if isinstance(album_row.get("album"), dict) else None,
            album_row.get("publishTime"),
        ):
            normalized = normalize_publish_time(candidate)
            if normalized:
                return normalized
        return ""

    def enrich_songs(self, songs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        source_rows = [dict(item) for item in songs if str(item.get("song_id") or "").strip()]
        if not source_rows:
            return []

        cached_map: Dict[str, Dict[str, Any]] = {}
        pending_ids: List[str] = []
        for row in source_rows:
            song_id = str(row.get("song_id") or "").strip()
            cached = self.repository.get_song_fact(song_id)
            if cached and str(cached.get("genre_status") or "").strip() == "known":
                cached_map[song_id] = cached
            else:
                pending_ids.append(song_id)

        song_detail_map: Dict[str, Dict[str, Any]] = {}
        for chunk in self._chunked(sorted(set(pending_ids)), 50):
            payload = self.api_client.get_song_detail(chunk)
            for song_row in payload.get("songs") or []:
                song_id = str(song_row.get("id") or "").strip()
                if song_id:
                    song_detail_map[song_id] = song_row

        album_publish_map: Dict[str, Dict[str, Any]] = {}
        album_song_links: Dict[str, List[str]] = defaultdict(list)
        for song_id, song_row in song_detail_map.items():
            album = song_row.get("al") or song_row.get("album") or {}
            album_id = str(album.get("id") or "").strip()
            if album_id:
                album_song_links[album_id].append(song_id)

        for album_id in album_song_links:
            try:
                album_publish_map[album_id] = self.api_client.get_album_detail(album_id)
            except Exception:
                album_publish_map[album_id] = {}

        for song_id, song_row in song_detail_map.items():
            album = song_row.get("al") or song_row.get("album") or {}
            artist_rows = song_row.get("ar") or song_row.get("artists") or []
            artist_names = self._normalize_artist_names(
                item.get("name") for item in artist_rows if isinstance(item, dict)
            )
            if not artist_names:
                fallback = next(
                    (
                        self._normalize_artist_names(source.get("artist_names") or [])
                        for source in source_rows
                        if str(source.get("song_id") or "").strip() == song_id
                    ),
                    [],
                )
                artist_names = fallback
            song_fact = {
                "song_id": song_id,
                "song_name": str(song_row.get("name") or "").strip(),
                "artist_names": artist_names,
                "album_id": str(album.get("id") or "").strip(),
                "album_name": str(album.get("name") or "").strip(),
                "publish_time": self._resolve_album_publish_time(
                    song_row,
                    album_publish_map.get(str(album.get("id") or "").strip(), {}),
                ),
            }
            tag_result = self.song_tagger.predict(song_fact)
            song_fact.update(
                {
                    "genre_label": str(tag_result.get("genre_label") or "未知"),
                    "genre_status": str(tag_result.get("genre_status") or "unknown"),
                    "genre_backend": str(tag_result.get("genre_backend") or ""),
                }
            )
            self.repository.upsert_song_fact(song_fact)
            cached_map[song_id] = song_fact

        enriched_rows: List[Dict[str, Any]] = []
        for row in source_rows:
            song_id = str(row.get("song_id") or "").strip()
            fact = cached_map.get(song_id) or {
                "song_id": song_id,
                "song_name": str(row.get("song_name") or "").strip(),
                "artist_names": self._normalize_artist_names(row.get("artist_names") or []),
                "album_id": "",
                "album_name": str(row.get("album_name") or "").strip(),
                "publish_time": "",
                "genre_label": "未知",
                "genre_status": "unknown",
                "genre_backend": "mapping_unavailable_v1",
            }
            enriched = dict(row)
            enriched.update(
                {
                    "song_name": fact.get("song_name") or enriched.get("song_name") or "",
                    "artist_names": fact.get("artist_names") or enriched.get("artist_names") or [],
                    "artist_name": "/".join(fact.get("artist_names") or enriched.get("artist_names") or []),
                    "album_id": fact.get("album_id") or "",
                    "album_name": fact.get("album_name") or "",
                    "publish_time": fact.get("publish_time") or "",
                    "genre_label": fact.get("genre_label") or "未知",
                    "genre_status": fact.get("genre_status") or "unknown",
                    "genre_backend": fact.get("genre_backend") or "",
                    "enrichment_status": "ok" if fact.get("song_name") else "partial",
                }
            )
            enriched_rows.append(enriched)
        return enriched_rows
