from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().casefold()


_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1F\x7F]")
_MULTI_SPACE_PATTERN = re.compile(r"\s+")
_EDGE_PUNCTUATION = " \t\r\n\"'“”‘’`~!@#$%^&*()_+-=[]{}|\\:;,./<>?，。！？、；：（）【】《》"


def _sanitize_unknown_text(value: Any) -> str:
    text = str(value or "")
    text = _CONTROL_CHAR_PATTERN.sub("", text)
    text = _MULTI_SPACE_PATTERN.sub(" ", text).strip()
    return text


def _normalize_unknown_text(value: Any) -> str:
    text = _sanitize_unknown_text(value)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.strip(_EDGE_PUNCTUATION)
    return text


def _normalize_artist_names(value: Any) -> List[str]:
    names = value if isinstance(value, list) else []
    normalized = [_normalize_text(item) for item in names if _normalize_text(item)]
    return sorted(dict.fromkeys(normalized))


def build_unknown_normalized_key(song_name: Any, artist_names: Iterable[Any], album_name: Any) -> str:
    normalized_artists = sorted(
        _normalize_unknown_text(item)
        for item in list(artist_names or [])
        if _normalize_unknown_text(item)
    )
    return f"{_normalize_unknown_text(song_name)}::{_normalize_unknown_text('|'.join(normalized_artists))}::{_normalize_unknown_text(album_name)}"


def build_song_dedupe_key(row: Dict[str, Any]) -> str:
    song_id = str(row.get("song_id") or "").strip()
    if song_id:
        return f"id:{song_id}"
    song_name = _normalize_text(row.get("song_name"))
    album_name = _normalize_text(row.get("album_name"))
    artist_names = _normalize_artist_names(row.get("artist_names") or row.get("artist_names_json"))
    artists_key = "|".join(artist_names)
    return f"meta:{song_name}::{artists_key}::{album_name}"


class SiteRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS friends (
                    uid TEXT PRIMARY KEY,
                    nickname TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT NOT NULL DEFAULT '',
                    synced_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recent_friends (
                    uid TEXT PRIMARY KEY,
                    friend_name TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT NOT NULL DEFAULT '',
                    last_used_at TEXT NOT NULL DEFAULT '',
                    is_pinned INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_messages (
                    uid TEXT NOT NULL,
                    msg_id TEXT NOT NULL,
                    msg_time_ms INTEGER NOT NULL,
                    msg_time_str TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    sender_uid TEXT NOT NULL DEFAULT '',
                    sender_name TEXT NOT NULL DEFAULT '',
                    msg_type TEXT NOT NULL DEFAULT '',
                    text_content TEXT NOT NULL DEFAULT '',
                    song_id TEXT NOT NULL DEFAULT '',
                    song_name TEXT NOT NULL DEFAULT '',
                    artist_name TEXT NOT NULL DEFAULT '',
                    raw_msg_json TEXT NOT NULL DEFAULT '',
                    archived_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (uid, msg_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS song_fact_cache (
                    song_id TEXT PRIMARY KEY,
                    song_name TEXT NOT NULL DEFAULT '',
                    artist_names_json TEXT NOT NULL DEFAULT '[]',
                    album_id TEXT NOT NULL DEFAULT '',
                    album_name TEXT NOT NULL DEFAULT '',
                    publish_time TEXT NOT NULL DEFAULT '',
                    genre_label TEXT NOT NULL DEFAULT '',
                    genre_status TEXT NOT NULL DEFAULT '',
                    genre_backend TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backfill_runs (
                    uid TEXT PRIMARY KEY,
                    last_backfill_at TEXT NOT NULL DEFAULT '',
                    oldest_archived_time TEXT NOT NULL DEFAULT '',
                    newest_archived_time TEXT NOT NULL DEFAULT '',
                    pages_fetched INTEGER NOT NULL DEFAULT 0,
                    fetched_count INTEGER NOT NULL DEFAULT 0,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consumption_state (
                    uid TEXT NOT NULL,
                    feature_scope TEXT NOT NULL,
                    last_consumed_msg_id TEXT NOT NULL DEFAULT '',
                    last_consumed_msg_time_ms INTEGER NOT NULL DEFAULT 0,
                    last_consumed_msg_time_str TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (uid, feature_scope)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_message_state (
                    uid TEXT NOT NULL,
                    feature_scope TEXT NOT NULL,
                    msg_id TEXT NOT NULL,
                    consumed_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (uid, feature_scope, msg_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_song_messages (
                    uid TEXT NOT NULL,
                    msg_id TEXT NOT NULL,
                    msg_time_ms INTEGER NOT NULL,
                    msg_time_str TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    sender_uid TEXT NOT NULL DEFAULT '',
                    sender_name TEXT NOT NULL DEFAULT '',
                    song_id TEXT NOT NULL DEFAULT '',
                    song_name TEXT NOT NULL DEFAULT '',
                    artist_name TEXT NOT NULL DEFAULT '',
                    artist_names_json TEXT NOT NULL DEFAULT '[]',
                    album_id TEXT NOT NULL DEFAULT '',
                    album_name TEXT NOT NULL DEFAULT '',
                    publish_time TEXT NOT NULL DEFAULT '',
                    genre_label TEXT NOT NULL DEFAULT '',
                    genre_status TEXT NOT NULL DEFAULT '',
                    genre_backend TEXT NOT NULL DEFAULT '',
                    enrichment_status TEXT NOT NULL DEFAULT '',
                    enriched_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (uid, msg_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_playlist_targets (
                    scope TEXT PRIMARY KEY,
                    playlist_id TEXT NOT NULL DEFAULT '',
                    playlist_name TEXT NOT NULL DEFAULT '',
                    strategy TEXT NOT NULL DEFAULT 'use_existing',
                    is_private INTEGER NOT NULL DEFAULT 0,
                    last_set_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_playlist_builds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT NOT NULL DEFAULT '',
                    friend_name TEXT NOT NULL DEFAULT '',
                    playlist_name TEXT NOT NULL DEFAULT '',
                    generated_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS relation_exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    export_type TEXT NOT NULL DEFAULT '',
                    target_uid TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    for_ai_json TEXT NOT NULL DEFAULT '{}',
                    prompt_text TEXT NOT NULL DEFAULT '',
                    external_copy_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS unknown_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_friend_uid TEXT NOT NULL DEFAULT '',
                    source_friend_name TEXT NOT NULL DEFAULT '',
                    msg_id TEXT NOT NULL DEFAULT '',
                    song_id TEXT NOT NULL DEFAULT '',
                    song_name TEXT NOT NULL DEFAULT '',
                    artist_names_json TEXT NOT NULL DEFAULT '[]',
                    album_name TEXT NOT NULL DEFAULT '',
                    detected_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_unknown_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    song_name TEXT NOT NULL DEFAULT '',
                    artist_names_json TEXT NOT NULL DEFAULT '[]',
                    album_name TEXT NOT NULL DEFAULT '',
                    normalized_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    first_seen_at TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL DEFAULT '',
                    upload_attempts INTEGER NOT NULL DEFAULT 0,
                    uploaded_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS unknown_song_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    song_name TEXT NOT NULL DEFAULT '',
                    artist_names_json TEXT NOT NULL DEFAULT '[]',
                    album_name TEXT NOT NULL DEFAULT '',
                    normalized_key TEXT NOT NULL DEFAULT '',
                    submit_count INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    first_seen_at TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL DEFAULT '',
                    last_submitted_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS unknown_submit_rate_limits (
                    client_ip TEXT PRIMARY KEY,
                    minute_bucket TEXT NOT NULL DEFAULT '',
                    request_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_uid_time ON raw_messages(uid, msg_time_ms)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_uid_type_time ON raw_messages(uid, msg_type, msg_time_ms)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_shared_song_messages_uid_time ON shared_song_messages(uid, msg_time_ms)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_shared_song_messages_uid_direction ON shared_song_messages(uid, direction)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_shared_song_messages_song_id ON shared_song_messages(song_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_recent_friends_last_used_at ON recent_friends(last_used_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_backfill_runs_uid ON backfill_runs(uid)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_consumption_state_uid_scope ON consumption_state(uid, feature_scope)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_feature_message_state_uid_scope ON feature_message_state(uid, feature_scope)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_relation_exports_type_target ON relation_exports(export_type, target_uid, created_at)")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_unknown_uploads_normalized_key ON pending_unknown_uploads(normalized_key)")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unknown_song_submissions_normalized_key ON unknown_song_submissions(normalized_key)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_unknown_song_submissions_status_time ON unknown_song_submissions(status, last_seen_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_unknown_song_submissions_submit_count ON unknown_song_submissions(submit_count DESC)")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unknown_queue_unique
                ON unknown_queue(source_friend_uid, song_name, artist_names_json, album_name)
                """
            )
            connection.commit()

    def upsert_friends(self, friends: Iterable[Dict[str, Any]]) -> None:
        synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [
            (
                str(item.get("uid") or "").strip(),
                str(item.get("nickname") or "").strip(),
                str(item.get("avatar_url") or "").strip(),
                synced_at,
            )
            for item in friends
            if str(item.get("uid") or "").strip()
        ]
        if not rows:
            return
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO friends (uid, nickname, avatar_url, synced_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    nickname=excluded.nickname,
                    avatar_url=excluded.avatar_url,
                    synced_at=excluded.synced_at
                """,
                rows,
            )
            connection.commit()

    def list_friends(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT uid, nickname, avatar_url, synced_at FROM friends ORDER BY lower(nickname), uid"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_archive_contact_uids(self) -> List[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT uid
                FROM raw_messages
                GROUP BY uid
                ORDER BY MAX(msg_time_ms) DESC, uid ASC
                """
            ).fetchall()
        return [str(row["uid"]).strip() for row in rows if str(row["uid"]).strip()]

    def list_friends_with_archive_contacts(self) -> List[Dict[str, Any]]:
        query = """
            SELECT
                f.uid AS uid,
                f.nickname AS nickname,
                f.avatar_url AS avatar_url,
                f.synced_at AS synced_at,
                MAX(r.msg_time_ms) AS last_message_ms,
                MAX(r.msg_time_str) AS last_message_at,
                COUNT(r.msg_id) AS message_count
            FROM friends f
            LEFT JOIN raw_messages r ON r.uid = f.uid
            GROUP BY f.uid, f.nickname, f.avatar_url, f.synced_at

            UNION

            SELECT
                r.uid AS uid,
                COALESCE(
                    NULLIF(MAX(CASE WHEN r.direction = 'friend' THEN r.sender_name ELSE '' END), ''),
                    '历史联系人'
                ) AS nickname,
                '' AS avatar_url,
                '' AS synced_at,
                MAX(r.msg_time_ms) AS last_message_ms,
                MAX(r.msg_time_str) AS last_message_at,
                COUNT(r.msg_id) AS message_count
            FROM raw_messages r
            LEFT JOIN friends f ON f.uid = r.uid
            WHERE f.uid IS NULL
            GROUP BY r.uid
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(query).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["message_count"] = int(payload.get("message_count") or 0)
            payload["last_message_ms"] = int(payload.get("last_message_ms") or 0)
            result.append(payload)
        result.sort(
            key=lambda item: (
                -int(item.get("last_message_ms") or 0),
                str(item.get("nickname") or "").lower(),
                str(item.get("uid") or ""),
            )
        )
        return result

    def list_recent_friends(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT uid, friend_name, avatar_url, last_used_at, is_pinned
                FROM recent_friends
                ORDER BY is_pinned DESC, last_used_at DESC, uid ASC
                """
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["is_pinned"] = bool(payload.get("is_pinned", 0))
            result.append(payload)
        return result

    def touch_recent_friend(self, uid: str, friend_name: str, avatar_url: str = "", max_items: int = 12) -> List[Dict[str, Any]]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            current = connection.execute(
                "SELECT uid, friend_name, avatar_url, last_used_at, is_pinned FROM recent_friends WHERE uid = ?",
                (uid,),
            ).fetchone()
            is_pinned = bool((dict(current) if current else {}).get("is_pinned", 0))
            connection.execute(
                """
                INSERT INTO recent_friends (uid, friend_name, avatar_url, last_used_at, is_pinned)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    friend_name=excluded.friend_name,
                    avatar_url=excluded.avatar_url,
                    last_used_at=excluded.last_used_at,
                    is_pinned=excluded.is_pinned
                """,
                (uid, friend_name, avatar_url, now, 1 if is_pinned else 0),
            )
            rows = connection.execute(
                """
                SELECT uid
                FROM recent_friends
                ORDER BY is_pinned DESC, last_used_at DESC, uid ASC
                """
            ).fetchall()
            overflow = [str(row["uid"]) for row in rows[max_items:]]
            if overflow:
                connection.executemany("DELETE FROM recent_friends WHERE uid = ?", [(item,) for item in overflow])
            connection.commit()
        return self.list_recent_friends()

    def pin_recent_friend(self, uid: str) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            connection.execute("UPDATE recent_friends SET is_pinned = 1 WHERE uid = ?", (uid,))
            connection.commit()
        return self.list_recent_friends()

    def unpin_recent_friend(self, uid: str) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            connection.execute("UPDATE recent_friends SET is_pinned = 0 WHERE uid = ?", (uid,))
            connection.commit()
        return self.list_recent_friends()

    def delete_recent_friend(self, uid: str) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM recent_friends WHERE uid = ?", (uid,))
            connection.commit()
        return self.list_recent_friends()

    def clear_recent_friends(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM recent_friends")
            connection.commit()
        return []

    def get_friend(self, uid: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT uid, nickname, avatar_url, synced_at FROM friends WHERE uid = ?",
                (uid,),
            ).fetchone()
        if row:
            return dict(row)
        with closing(self._connect()) as connection:
            fallback = connection.execute(
                """
                SELECT
                    uid,
                    COALESCE(NULLIF(MAX(CASE WHEN direction = 'friend' THEN sender_name ELSE '' END), ''), '历史联系人') AS nickname,
                    '' AS avatar_url,
                    '' AS synced_at
                FROM raw_messages
                WHERE uid = ?
                GROUP BY uid
                """,
                (uid,),
            ).fetchone()
        return dict(fallback) if fallback else None

    def upsert_raw_messages(self, rows: Iterable[Dict[str, Any]]) -> int:
        archived_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        normalized_rows = [
            (
                str(item.get("uid") or "").strip(),
                str(item.get("msg_id") or "").strip(),
                int(item.get("msg_time_ms") or 0),
                str(item.get("msg_time_str") or "").strip(),
                str(item.get("direction") or "").strip(),
                str(item.get("sender_uid") or "").strip(),
                str(item.get("sender_name") or "").strip(),
                str(item.get("msg_type") or "").strip(),
                str(item.get("text_content") or "").strip(),
                str(item.get("song_id") or "").strip(),
                str(item.get("song_name") or "").strip(),
                str(item.get("artist_name") or "").strip(),
                str(item.get("raw_msg_json") or "").strip(),
                archived_at,
            )
            for item in rows
            if str(item.get("uid") or "").strip() and str(item.get("msg_id") or "").strip()
        ]
        if not normalized_rows:
            return 0
        existing_keys: set[tuple[str, str]] = set()
        grouped_msg_ids: Dict[str, List[str]] = {}
        for uid, msg_id, *_ in normalized_rows:
            grouped_msg_ids.setdefault(uid, []).append(msg_id)
        with closing(self._connect()) as connection:
            for uid, msg_ids in grouped_msg_ids.items():
                placeholders = ",".join("?" for _ in msg_ids)
                query = f"SELECT uid, msg_id FROM raw_messages WHERE uid = ? AND msg_id IN ({placeholders})"
                rows = connection.execute(query, [uid, *msg_ids]).fetchall()
                existing_keys.update((str(row["uid"]), str(row["msg_id"])) for row in rows)
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO raw_messages (
                    uid, msg_id, msg_time_ms, msg_time_str, direction, sender_uid, sender_name,
                    msg_type, text_content, song_id, song_name, artist_name, raw_msg_json, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid, msg_id) DO UPDATE SET
                    msg_time_ms=excluded.msg_time_ms,
                    msg_time_str=excluded.msg_time_str,
                    direction=excluded.direction,
                    sender_uid=excluded.sender_uid,
                    sender_name=excluded.sender_name,
                    msg_type=excluded.msg_type,
                    text_content=excluded.text_content,
                    song_id=excluded.song_id,
                    song_name=excluded.song_name,
                    artist_name=excluded.artist_name,
                    raw_msg_json=excluded.raw_msg_json,
                    archived_at=excluded.archived_at
                """,
                normalized_rows,
            )
            connection.commit()
        inserted_count = 0
        seen_keys: set[tuple[str, str]] = set()
        for uid, msg_id, *_ in normalized_rows:
            key = (uid, msg_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if key not in existing_keys:
                inserted_count += 1
        return inserted_count

    def query_raw_messages(
        self,
        uid: str,
        *,
        direction: str | None = None,
        msg_type: str | None = None,
        keyword: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT uid, msg_id, msg_time_ms, msg_time_str, direction, sender_uid, sender_name,
                   msg_type, text_content, song_id, song_name, artist_name, raw_msg_json, archived_at
            FROM raw_messages
            WHERE uid = ?
        """
        params: List[Any] = [uid]
        if direction and direction != "all":
            query += " AND direction = ?"
            params.append(direction)
        if msg_type and msg_type != "all":
            query += " AND msg_type = ?"
            params.append(msg_type)
        if start_datetime:
            query += " AND msg_time_str >= ?"
            params.append(start_datetime)
        if end_datetime:
            query += " AND msg_time_str <= ?"
            params.append(end_datetime)
        if keyword:
            like_value = f"%{keyword}%"
            query += """
                AND (
                    text_content LIKE ?
                    OR song_name LIKE ?
                    OR artist_name LIKE ?
                    OR sender_name LIKE ?
                )
            """
            params.extend([like_value, like_value, like_value, like_value])
        query += " ORDER BY msg_time_ms ASC, msg_id ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def latest_raw_message_time_ms(self, uid: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT MAX(msg_time_ms) AS latest_time FROM raw_messages WHERE uid = ?",
                (uid,),
            ).fetchone()
        return int((row["latest_time"] if row and row["latest_time"] is not None else 0) or 0)

    def get_latest_message(self, uid: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT uid, msg_id, msg_time_ms, msg_time_str, direction, sender_uid, sender_name,
                       msg_type, text_content, song_id, song_name, artist_name, raw_msg_json, archived_at
                FROM raw_messages
                WHERE uid = ?
                ORDER BY msg_time_ms DESC, msg_id DESC
                LIMIT 1
                """,
                (uid,),
            ).fetchone()
        return dict(row) if row else None

    def count_raw_messages(self, uid: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(1) AS total_count FROM raw_messages WHERE uid = ?",
                (uid,),
            ).fetchone()
        return int((row["total_count"] if row and row["total_count"] is not None else 0) or 0)

    def count_shared_song_messages(
        self,
        uid: str,
        *,
        known_only: bool = False,
        unknown_only: bool = False,
        distinct_song_ids: bool = False,
    ) -> int:
        count_expr = "COUNT(DISTINCT song_id)" if distinct_song_ids else "COUNT(1)"
        query = f"SELECT {count_expr} AS total_count FROM shared_song_messages WHERE uid = ?"
        params: List[Any] = [uid]
        if known_only:
            query += " AND genre_status = 'known'"
        if unknown_only:
            query += " AND genre_status = 'unknown'"
        if distinct_song_ids:
            query += " AND TRIM(song_id) <> ''"
        with closing(self._connect()) as connection:
            row = connection.execute(query, params).fetchone()
        return int((row["total_count"] if row and row["total_count"] is not None else 0) or 0)

    @staticmethod
    def dedupe_song_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            payload = dict(row)
            if isinstance(payload.get("artist_names_json"), str) and not payload.get("artist_names"):
                try:
                    payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
                except json.JSONDecodeError:
                    payload["artist_names"] = []
            key = build_song_dedupe_key(payload)
            existing = deduped.get(key)
            if not existing:
                deduped[key] = payload
                continue
            existing_known = str(existing.get("genre_status") or "") == "known"
            payload_known = str(payload.get("genre_status") or "") == "known"
            existing_time = int(existing.get("msg_time_ms") or 0)
            payload_time = int(payload.get("msg_time_ms") or 0)
            if payload_known and not existing_known:
                deduped[key] = payload
                continue
            if payload_known == existing_known and payload_time > existing_time:
                deduped[key] = payload
        return list(deduped.values())

    def count_distinct_shared_songs(
        self,
        uid: str,
        *,
        known_only: bool = False,
        unknown_only: bool = False,
        direction: str | None = None,
    ) -> int:
        rows = self.query_shared_song_messages(uid, direction=direction, known_only=False)
        deduped = self.dedupe_song_rows(rows)
        if unknown_only:
            return len([row for row in deduped if str(row.get("genre_status") or "") == "unknown"])
        if known_only:
            return len([row for row in deduped if str(row.get("genre_status") or "") == "known"])
        return len(deduped)

    def distinct_shared_song_rows(
        self,
        uid: str,
        *,
        known_only: bool = False,
        direction: str | None = None,
    ) -> List[Dict[str, Any]]:
        rows = self.query_shared_song_messages(uid, direction=direction, known_only=known_only)
        deduped = self.dedupe_song_rows(rows)
        if known_only:
            return [row for row in deduped if str(row.get("genre_status") or "") == "known"]
        return deduped

    def distinct_all_shared_song_rows(self, *, known_only: bool = False) -> List[Dict[str, Any]]:
        rows = self.query_all_shared_song_messages(known_only=known_only)
        deduped = self.dedupe_song_rows(rows)
        if known_only:
            return [row for row in deduped if str(row.get("genre_status") or "") == "known"]
        return deduped

    def get_archive_range(self, uid: str) -> Dict[str, Optional[str]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT MIN(msg_time_str) AS oldest_archived_time,
                       MAX(msg_time_str) AS newest_archived_time
                FROM raw_messages
                WHERE uid = ?
                """,
                (uid,),
            ).fetchone()
        return {
            "oldest_archived_time": row["oldest_archived_time"] if row else None,
            "newest_archived_time": row["newest_archived_time"] if row else None,
        }

    def get_backfill_status(self, uid: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT uid, last_backfill_at, oldest_archived_time, newest_archived_time,
                       pages_fetched, fetched_count, inserted_count, status
                FROM backfill_runs
                WHERE uid = ?
                """,
                (uid,),
            ).fetchone()
        return dict(row) if row else None

    def save_backfill_status(
        self,
        uid: str,
        status: str,
        pages_fetched: int,
        fetched_count: int,
        inserted_count: int,
        oldest_archived_time: Optional[str],
        newest_archived_time: Optional[str],
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO backfill_runs (
                    uid, last_backfill_at, oldest_archived_time, newest_archived_time,
                    pages_fetched, fetched_count, inserted_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    last_backfill_at=excluded.last_backfill_at,
                    oldest_archived_time=excluded.oldest_archived_time,
                    newest_archived_time=excluded.newest_archived_time,
                    pages_fetched=excluded.pages_fetched,
                    fetched_count=excluded.fetched_count,
                    inserted_count=excluded.inserted_count,
                    status=excluded.status
                """,
                (
                    uid,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    str(oldest_archived_time or ""),
                    str(newest_archived_time or ""),
                    pages_fetched,
                    fetched_count,
                    inserted_count,
                    status,
                ),
            )
            connection.commit()

    def get_consumption_state(self, uid: str, feature_scope: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT uid, feature_scope, last_consumed_msg_id, last_consumed_msg_time_ms,
                       last_consumed_msg_time_str, updated_at
                FROM consumption_state
                WHERE uid = ? AND feature_scope = ?
                """,
                (uid, feature_scope),
            ).fetchone()
        return dict(row) if row else None

    def save_consumption_state(
        self,
        uid: str,
        feature_scope: str,
        last_consumed_msg_id: str,
        last_consumed_msg_time_ms: int,
        last_consumed_msg_time_str: str,
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO consumption_state (
                    uid, feature_scope, last_consumed_msg_id, last_consumed_msg_time_ms,
                    last_consumed_msg_time_str, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid, feature_scope) DO UPDATE SET
                    last_consumed_msg_id=excluded.last_consumed_msg_id,
                    last_consumed_msg_time_ms=excluded.last_consumed_msg_time_ms,
                    last_consumed_msg_time_str=excluded.last_consumed_msg_time_str,
                    updated_at=excluded.updated_at
                """,
                (
                    uid,
                    feature_scope,
                    last_consumed_msg_id,
                    last_consumed_msg_time_ms,
                    last_consumed_msg_time_str,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            connection.commit()

    def advance_consumption_state(
        self,
        uid: str,
        feature_scope: str,
        last_consumed_msg_id: str,
        last_consumed_msg_time_ms: int,
        last_consumed_msg_time_str: str,
    ) -> bool:
        current = self.get_consumption_state(uid=uid, feature_scope=feature_scope)
        current_time_ms = int((current or {}).get("last_consumed_msg_time_ms") or 0)
        current_msg_id = str((current or {}).get("last_consumed_msg_id") or "")
        next_time_ms = int(last_consumed_msg_time_ms or 0)
        next_msg_id = str(last_consumed_msg_id or "")
        if current and (next_time_ms, next_msg_id) <= (current_time_ms, current_msg_id):
            return False
        self.save_consumption_state(
            uid=uid,
            feature_scope=feature_scope,
            last_consumed_msg_id=next_msg_id,
            last_consumed_msg_time_ms=next_time_ms,
            last_consumed_msg_time_str=str(last_consumed_msg_time_str or ""),
        )
        return True

    def mark_messages_consumed(self, uid: str, feature_scope: str, msg_ids: List[str]) -> None:
        if not msg_ids:
            return
        consumed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO feature_message_state (
                    uid, feature_scope, msg_id, consumed_at
                ) VALUES (?, ?, ?, ?)
                """,
                [(uid, feature_scope, msg_id, consumed_at) for msg_id in msg_ids],
            )
            connection.commit()

    def delete_friend_archive(self, uid: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM raw_messages WHERE uid = ?", (uid,))
            connection.execute("DELETE FROM shared_song_messages WHERE uid = ?", (uid,))
            connection.execute("DELETE FROM unknown_queue WHERE source_friend_uid = ?", (uid,))
            connection.execute("DELETE FROM backfill_runs WHERE uid = ?", (uid,))
            connection.execute("DELETE FROM consumption_state WHERE uid = ?", (uid,))
            connection.execute("DELETE FROM feature_message_state WHERE uid = ?", (uid,))
            connection.commit()

    def list_raw_message_active_dates(self, uid: str) -> List[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT substr(msg_time_str, 1, 10) AS active_date
                FROM raw_messages
                WHERE uid = ? AND msg_time_str != ''
                ORDER BY active_date ASC
                """,
                (uid,),
            ).fetchall()
        return [str(row["active_date"]) for row in rows if row["active_date"]]

    def upsert_song_fact(self, row: Dict[str, Any]) -> None:
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO song_fact_cache (
                    song_id, song_name, artist_names_json, album_id, album_name,
                    publish_time, genre_label, genre_status, genre_backend, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(song_id) DO UPDATE SET
                    song_name=excluded.song_name,
                    artist_names_json=excluded.artist_names_json,
                    album_id=excluded.album_id,
                    album_name=excluded.album_name,
                    publish_time=excluded.publish_time,
                    genre_label=excluded.genre_label,
                    genre_status=excluded.genre_status,
                    genre_backend=excluded.genre_backend,
                    updated_at=excluded.updated_at
                """,
                (
                    str(row.get("song_id") or "").strip(),
                    str(row.get("song_name") or "").strip(),
                    json.dumps(list(row.get("artist_names") or []), ensure_ascii=False),
                    str(row.get("album_id") or "").strip(),
                    str(row.get("album_name") or "").strip(),
                    str(row.get("publish_time") or "").strip(),
                    str(row.get("genre_label") or "").strip(),
                    str(row.get("genre_status") or "").strip(),
                    str(row.get("genre_backend") or "").strip(),
                    updated_at,
                ),
            )
            connection.commit()

    def get_song_fact(self, song_id: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT song_id, song_name, artist_names_json, album_id, album_name,
                       publish_time, genre_label, genre_status, genre_backend, updated_at
                FROM song_fact_cache
                WHERE song_id = ?
                """,
                (song_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
        return payload

    def list_song_facts(self, *, genre_status: str | None = None) -> List[Dict[str, Any]]:
        query = """
            SELECT song_id, song_name, artist_names_json, album_id, album_name,
                   publish_time, genre_label, genre_status, genre_backend, updated_at
            FROM song_fact_cache
        """
        params: List[Any] = []
        if genre_status:
            query += " WHERE genre_status = ?"
            params.append(str(genre_status).strip())
        query += " ORDER BY updated_at ASC, song_id ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def upsert_shared_song_message(self, row: Dict[str, Any]) -> bool:
        enriched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uid = str(row.get("uid") or "").strip()
        msg_id = str(row.get("msg_id") or "").strip()
        existed = False
        with closing(self._connect()) as connection:
            existed = (
                connection.execute(
                    "SELECT 1 FROM shared_song_messages WHERE uid = ? AND msg_id = ?",
                    (uid, msg_id),
                ).fetchone()
                is not None
            )
            connection.execute(
                """
                INSERT INTO shared_song_messages (
                    uid, msg_id, msg_time_ms, msg_time_str, direction, sender_uid, sender_name,
                    song_id, song_name, artist_name, artist_names_json, album_id, album_name,
                    publish_time, genre_label, genre_status, genre_backend, enrichment_status, enriched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid, msg_id) DO UPDATE SET
                    msg_time_ms=excluded.msg_time_ms,
                    msg_time_str=excluded.msg_time_str,
                    direction=excluded.direction,
                    sender_uid=excluded.sender_uid,
                    sender_name=excluded.sender_name,
                    song_id=excluded.song_id,
                    song_name=excluded.song_name,
                    artist_name=excluded.artist_name,
                    artist_names_json=excluded.artist_names_json,
                    album_id=excluded.album_id,
                    album_name=excluded.album_name,
                    publish_time=excluded.publish_time,
                    genre_label=excluded.genre_label,
                    genre_status=excluded.genre_status,
                    genre_backend=excluded.genre_backend,
                    enrichment_status=excluded.enrichment_status,
                    enriched_at=excluded.enriched_at
                """,
                (
                    uid,
                    msg_id,
                    int(row.get("msg_time_ms") or 0),
                    str(row.get("msg_time_str") or "").strip(),
                    str(row.get("direction") or "").strip(),
                    str(row.get("sender_uid") or "").strip(),
                    str(row.get("sender_name") or "").strip(),
                    str(row.get("song_id") or "").strip(),
                    str(row.get("song_name") or "").strip(),
                    str(row.get("artist_name") or "").strip(),
                    json.dumps(list(row.get("artist_names") or []), ensure_ascii=False),
                    str(row.get("album_id") or "").strip(),
                    str(row.get("album_name") or "").strip(),
                    str(row.get("publish_time") or "").strip(),
                    str(row.get("genre_label") or "").strip(),
                    str(row.get("genre_status") or "").strip(),
                    str(row.get("genre_backend") or "").strip(),
                    str(row.get("enrichment_status") or "").strip(),
                    enriched_at,
                ),
            )
            connection.commit()
        return not existed

    def query_shared_song_messages(
        self,
        uid: str,
        *,
        direction: str | None = None,
        keyword: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        known_only: bool = False,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT uid, msg_id, msg_time_ms, msg_time_str, direction, sender_uid, sender_name,
                   song_id, song_name, artist_name, artist_names_json, album_id, album_name,
                   publish_time, genre_label, genre_status, genre_backend, enrichment_status, enriched_at
            FROM shared_song_messages
            WHERE uid = ?
        """
        params: List[Any] = [uid]
        if direction and direction != "all":
            query += " AND direction = ?"
            params.append(direction)
        if start_datetime:
            query += " AND msg_time_str >= ?"
            params.append(start_datetime)
        if end_datetime:
            query += " AND msg_time_str <= ?"
            params.append(end_datetime)
        if known_only:
            query += " AND genre_status = 'known'"
        if keyword:
            like_value = f"%{keyword}%"
            query += """
                AND (
                    song_name LIKE ?
                    OR artist_name LIKE ?
                    OR album_name LIKE ?
                    OR sender_name LIKE ?
                    OR genre_label LIKE ?
                )
            """
            params.extend([like_value, like_value, like_value, like_value, like_value])
        query += " ORDER BY msg_time_ms ASC, msg_id ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def query_all_shared_song_messages(self, *, known_only: bool = False) -> List[Dict[str, Any]]:
        query = """
            SELECT uid, msg_id, msg_time_ms, msg_time_str, direction, sender_uid, sender_name,
                   song_id, song_name, artist_name, artist_names_json, album_id, album_name,
                   publish_time, genre_label, genre_status, genre_backend, enrichment_status, enriched_at
            FROM shared_song_messages
        """
        params: List[Any] = []
        if known_only:
            query += " WHERE genre_status = 'known'"
        query += " ORDER BY uid ASC, msg_time_ms ASC, msg_id ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def list_shared_song_active_dates(self, uid: str) -> List[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT substr(msg_time_str, 1, 10) AS active_date
                FROM shared_song_messages
                WHERE uid = ? AND msg_time_str != ''
                ORDER BY active_date ASC
                """,
                (uid,),
            ).fetchall()
        return [str(row["active_date"]) for row in rows if row["active_date"]]

    def upsert_unknown(self, row: Dict[str, Any]) -> None:
        detected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO unknown_queue (
                    source_friend_uid, source_friend_name, msg_id, song_id, song_name,
                    artist_names_json, album_name, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("source_friend_uid") or "").strip(),
                    str(row.get("source_friend_name") or "").strip(),
                    str(row.get("msg_id") or "").strip(),
                    str(row.get("song_id") or "").strip(),
                    str(row.get("song_name") or "").strip(),
                    json.dumps(list(row.get("artist_names") or []), ensure_ascii=False),
                    str(row.get("album_name") or "").strip(),
                    detected_at,
                ),
            )
            connection.commit()

    def clear_unknown_queue(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM unknown_queue")
            connection.commit()

    def clear_unknown_queue_for_friend(self, uid: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM unknown_queue WHERE source_friend_uid = ?", (uid,))
            connection.commit()

    def list_unknown_rows(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT source_friend_uid, source_friend_name, msg_id, song_id, song_name, artist_names_json, album_name, detected_at
                FROM unknown_queue
                ORDER BY detected_at ASC, source_friend_uid ASC, msg_id ASC
                """
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def list_distinct_unknown_song_candidates(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    MIN(song_id) AS song_id,
                    song_name,
                    artist_names_json,
                    MIN(album_id) AS album_id,
                    album_name,
                    MIN(publish_time) AS publish_time
                FROM shared_song_messages
                WHERE genre_status = 'unknown'
                GROUP BY song_name, artist_names_json, album_name
                ORDER BY MAX(msg_time_ms) DESC, song_name ASC
                """
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def upsert_pending_unknown_upload(self, row: Dict[str, Any]) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        normalized_key = str(row.get("normalized_key") or "").strip()
        if not normalized_key:
            return
        with closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT id, status, upload_attempts FROM pending_unknown_uploads WHERE normalized_key = ?",
                (normalized_key,),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE pending_unknown_uploads
                    SET song_name = ?, artist_names_json = ?, album_name = ?, status = 'pending', last_seen_at = ?
                    WHERE normalized_key = ?
                    """,
                    (
                        str(row.get("song_name") or "").strip(),
                        json.dumps(list(row.get("artist_names") or []), ensure_ascii=False),
                        str(row.get("album_name") or "").strip(),
                        now,
                        normalized_key,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO pending_unknown_uploads (
                        song_name, artist_names_json, album_name, normalized_key, status,
                        first_seen_at, last_seen_at, upload_attempts, uploaded_at
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?, 0, '')
                    """,
                    (
                        str(row.get("song_name") or "").strip(),
                        json.dumps(list(row.get("artist_names") or []), ensure_ascii=False),
                        str(row.get("album_name") or "").strip(),
                        normalized_key,
                        now,
                        now,
                    ),
                )
            connection.commit()

    def list_pending_unknown_uploads(self, *, statuses: List[str], limit: int) -> List[Dict[str, Any]]:
        placeholders = ",".join("?" for _ in statuses)
        query = f"""
            SELECT id, song_name, artist_names_json, album_name, normalized_key, status,
                   first_seen_at, last_seen_at, upload_attempts, uploaded_at
            FROM pending_unknown_uploads
            WHERE status IN ({placeholders})
            ORDER BY first_seen_at ASC, id ASC
            LIMIT ?
        """
        params: List[Any] = [*statuses, int(limit)]
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def get_pending_unknown_upload_stats(self) -> Dict[str, int]:
        stats = {"pending": 0, "uploaded": 0, "failed": 0, "total": 0}
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM pending_unknown_uploads
                GROUP BY status
                """
            ).fetchall()
            total_row = connection.execute("SELECT COUNT(*) AS count FROM pending_unknown_uploads").fetchone()
            unknown_row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM (
                    SELECT 1
                    FROM shared_song_messages
                    WHERE genre_status = 'unknown'
                    GROUP BY song_name, artist_names_json, album_name
                )
                """
            ).fetchone()
        stats["total"] = int((dict(total_row) if total_row else {}).get("count") or 0)
        for row in rows:
            payload = dict(row)
            status = str(payload.get("status") or "")
            if status in stats:
                stats[status] = int(payload.get("count") or 0)
        stats["current_unknown_total"] = int((dict(unknown_row) if unknown_row else {}).get("count") or 0)
        stats["uploaded_deduped"] = stats["uploaded"]
        return stats

    def mark_pending_unknown_uploads_uploaded(self, ids: List[int]) -> None:
        if not ids:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                UPDATE pending_unknown_uploads
                SET status = 'uploaded', uploaded_at = ?, last_seen_at = ?
                WHERE id = ?
                """,
                [(now, now, item_id) for item_id in ids],
            )
            connection.commit()

    def mark_pending_unknown_uploads_failed(self, ids: List[int]) -> None:
        if not ids:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                UPDATE pending_unknown_uploads
                SET status = 'failed', upload_attempts = upload_attempts + 1, last_seen_at = ?
                WHERE id = ?
                """,
                [(now, item_id) for item_id in ids],
            )
            connection.commit()

    def enforce_unknown_submit_rate_limit(self, *, client_ip: str, limit_per_minute: int) -> None:
        minute_bucket = datetime.now().strftime("%Y-%m-%d %H:%M")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT minute_bucket, request_count FROM unknown_submit_rate_limits WHERE client_ip = ?",
                (client_ip,),
            ).fetchone()
            if not row:
                connection.execute(
                    """
                    INSERT INTO unknown_submit_rate_limits (client_ip, minute_bucket, request_count, updated_at)
                    VALUES (?, ?, 1, ?)
                    """,
                    (client_ip, minute_bucket, now),
                )
                connection.commit()
                return
            current_bucket = str(row["minute_bucket"] or "")
            request_count = int(row["request_count"] or 0)
            if current_bucket != minute_bucket:
                connection.execute(
                    """
                    UPDATE unknown_submit_rate_limits
                    SET minute_bucket = ?, request_count = 1, updated_at = ?
                    WHERE client_ip = ?
                    """,
                    (minute_bucket, now, client_ip),
                )
                connection.commit()
                return
            if request_count >= limit_per_minute:
                raise ValueError("提交过于频繁，请稍后再试。")
            connection.execute(
                """
                UPDATE unknown_submit_rate_limits
                SET request_count = request_count + 1, updated_at = ?
                WHERE client_ip = ?
                """,
                (now, client_ip),
            )
            connection.commit()

    def get_unknown_song_submission_by_key(self, normalized_key: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT id, song_name, artist_names_json, album_name, normalized_key, submit_count,
                       status, first_seen_at, last_seen_at, last_submitted_at, created_at, updated_at
                FROM unknown_song_submissions
                WHERE normalized_key = ?
                """,
                (normalized_key,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
        return payload

    def insert_unknown_song_submission(self, row: Dict[str, Any], *, now: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO unknown_song_submissions (
                    song_name, artist_names_json, album_name, normalized_key, submit_count, status,
                    first_seen_at, last_seen_at, last_submitted_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, 'pending', ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("song_name") or "").strip(),
                    json.dumps(list(row.get("artist_names") or []), ensure_ascii=False),
                    str(row.get("album_name") or "").strip(),
                    str(row.get("normalized_key") or "").strip(),
                    now,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            connection.commit()

    def touch_unknown_song_submission(self, normalized_key: str, *, now: str, increment_submit_count: bool) -> None:
        with closing(self._connect()) as connection:
            if increment_submit_count:
                connection.execute(
                    """
                    UPDATE unknown_song_submissions
                    SET submit_count = submit_count + 1,
                        last_seen_at = ?,
                        last_submitted_at = ?,
                        updated_at = ?
                    WHERE normalized_key = ?
                    """,
                    (now, now, now, normalized_key),
                )
            else:
                connection.execute(
                    """
                    UPDATE unknown_song_submissions
                    SET last_submitted_at = ?, updated_at = ?
                    WHERE normalized_key = ?
                    """,
                    (now, now, normalized_key),
                )
            connection.commit()

    def list_unknown_song_submissions(self, *, status: Optional[str]) -> List[Dict[str, Any]]:
        query = """
            SELECT id, song_name, artist_names_json, album_name, normalized_key, submit_count,
                   status, first_seen_at, last_seen_at, last_submitted_at, created_at, updated_at
            FROM unknown_song_submissions
        """
        params: List[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY last_seen_at ASC, id ASC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def get_unknown_song_submission_stats(self) -> Dict[str, Any]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM unknown_song_submissions
                GROUP BY status
                """
            ).fetchall()
            total_row = connection.execute("SELECT COUNT(*) AS count FROM unknown_song_submissions").fetchone()
        stats = {"total": int((dict(total_row) if total_row else {}).get("count") or 0)}
        for row in rows:
            payload = dict(row)
            stats[str(payload.get("status") or "pending")] = int(payload.get("count") or 0)
        return stats

    def list_top_unknown_song_submissions(self, *, limit: int) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT song_name, artist_names_json, album_name, normalized_key, submit_count, status, last_seen_at
                FROM unknown_song_submissions
                ORDER BY submit_count DESC, last_seen_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["artist_names"] = json.loads(str(payload.get("artist_names_json") or "[]"))
            result.append(payload)
        return result

    def update_unknown_song_submission_status(self, *, from_status: Optional[str], to_status: str) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            if from_status:
                cursor = connection.execute(
                    "UPDATE unknown_song_submissions SET status = ?, updated_at = ? WHERE status = ?",
                    (to_status, now, from_status),
                )
            else:
                cursor = connection.execute(
                    "UPDATE unknown_song_submissions SET status = ?, updated_at = ?",
                    (to_status, now),
                )
            connection.commit()
        return int(cursor.rowcount or 0)

    def update_unknown_song_submission_status_by_keys(self, *, keys: List[str], to_status: str) -> int:
        if not keys:
            return 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            cursor = connection.executemany(
                "UPDATE unknown_song_submissions SET status = ?, updated_at = ? WHERE normalized_key = ?",
                [(to_status, now, key) for key in keys],
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def delete_unknown_song_submissions_by_status(self, status: str) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM unknown_song_submissions WHERE status = ?", (status,))
            connection.commit()
        return int(cursor.rowcount or 0)

    def remove_unknown_by_song(self, song_id: str) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM unknown_queue WHERE song_id = ?",
                (str(song_id).strip(),),
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def remove_pending_unknown_upload_by_song_fact(self, song_fact: Dict[str, Any]) -> int:
        normalized_key = build_unknown_normalized_key(
            song_fact.get("song_name"),
            song_fact.get("artist_names") or [],
            song_fact.get("album_name"),
        )
        if not normalized_key:
            return 0
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                DELETE FROM pending_unknown_uploads
                WHERE normalized_key = ?
                """,
                (normalized_key,),
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def sync_song_fact_to_shared_messages(self, song_fact: Dict[str, Any]) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE shared_song_messages
                SET song_name = ?,
                    artist_name = ?,
                    artist_names_json = ?,
                    album_id = ?,
                    album_name = ?,
                    publish_time = ?,
                    genre_label = ?,
                    genre_status = ?,
                    genre_backend = ?,
                    enriched_at = ?
                WHERE song_id = ?
                """,
                (
                    str(song_fact.get("song_name") or "").strip(),
                    "/".join(list(song_fact.get("artist_names") or [])),
                    json.dumps(list(song_fact.get("artist_names") or []), ensure_ascii=False),
                    str(song_fact.get("album_id") or "").strip(),
                    str(song_fact.get("album_name") or "").strip(),
                    str(song_fact.get("publish_time") or "").strip(),
                    str(song_fact.get("genre_label") or "").strip(),
                    str(song_fact.get("genre_status") or "").strip(),
                    str(song_fact.get("genre_backend") or "").strip(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    str(song_fact.get("song_id") or "").strip(),
                ),
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def sync_shared_song_messages_by_metadata(self, song_fact: Dict[str, Any]) -> int:
        song_name = str(song_fact.get("song_name") or "").strip()
        album_name = str(song_fact.get("album_name") or "").strip()
        artist_names_json = json.dumps(list(song_fact.get("artist_names") or []), ensure_ascii=False)
        if not song_name:
            return 0
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE shared_song_messages
                SET genre_label = ?,
                    genre_status = ?,
                    genre_backend = ?,
                    enriched_at = ?
                WHERE song_name = ?
                  AND artist_names_json = ?
                  AND album_name = ?
                  AND genre_status = 'unknown'
                """,
                (
                    str(song_fact.get("genre_label") or "").strip(),
                    str(song_fact.get("genre_status") or "").strip(),
                    str(song_fact.get("genre_backend") or "").strip(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    song_name,
                    artist_names_json,
                    album_name,
                ),
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def remove_unknown_by_song_metadata(self, song_fact: Dict[str, Any]) -> int:
        song_name = str(song_fact.get("song_name") or "").strip()
        album_name = str(song_fact.get("album_name") or "").strip()
        artist_names_json = json.dumps(list(song_fact.get("artist_names") or []), ensure_ascii=False)
        if not song_name:
            return 0
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                DELETE FROM unknown_queue
                WHERE song_name = ? AND artist_names_json = ? AND album_name = ?
                """,
                (song_name, artist_names_json, album_name),
            )
            connection.commit()
        return int(cursor.rowcount or 0)

    def save_shadow_playlist_target(self, payload: Dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO shadow_playlist_targets (scope, playlist_id, playlist_name, strategy, is_private, last_set_at)
                VALUES ('default', ?, ?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                    playlist_id=excluded.playlist_id,
                    playlist_name=excluded.playlist_name,
                    strategy=excluded.strategy,
                    is_private=excluded.is_private,
                    last_set_at=excluded.last_set_at
                """,
                (
                    str(payload.get("playlist_id") or "").strip(),
                    str(payload.get("playlist_name") or "").strip(),
                    str(payload.get("strategy") or "use_existing").strip(),
                    1 if bool(payload.get("is_private", False)) else 0,
                    str(payload.get("last_set_at") or "").strip(),
                ),
            )
            connection.commit()

    def get_shadow_playlist_target(self) -> Dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT playlist_id, playlist_name, strategy, is_private, last_set_at
                FROM shadow_playlist_targets
                WHERE scope = 'default'
                """
            ).fetchone()
        if not row:
            return {
                "playlist_id": "",
                "playlist_name": "",
                "strategy": "use_existing",
                "is_private": False,
                "last_set_at": "",
            }
        payload = dict(row)
        payload["is_private"] = bool(payload.get("is_private", 0))
        return payload

    def save_shadow_playlist_build(self, payload: Dict[str, Any]) -> None:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO shadow_playlist_builds (
                    uid, friend_name, playlist_name, generated_count, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("uid") or "").strip(),
                    str(payload.get("friend_name") or "").strip(),
                    str(payload.get("playlist_name") or "").strip(),
                    int(payload.get("generated_count") or 0),
                    json.dumps(payload, ensure_ascii=False),
                    created_at,
                ),
            )
            connection.commit()

    def get_last_shadow_playlist_build(self) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT uid, friend_name, playlist_name, generated_count, payload_json, created_at
                FROM shadow_playlist_builds
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        try:
            payload["payload_json"] = json.loads(str(payload.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            payload["payload_json"] = {}
        return payload

    def list_shadow_playlist_builds(self, uid: str | None = None) -> List[Dict[str, Any]]:
        query = """
            SELECT uid, friend_name, playlist_name, generated_count, payload_json, created_at
            FROM shadow_playlist_builds
        """
        params: List[Any] = []
        if uid:
            query += " WHERE uid = ?"
            params.append(uid)
        query += " ORDER BY id DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            try:
                payload["payload_json"] = json.loads(str(payload.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                payload["payload_json"] = {}
            result.append(payload)
        return result

    def save_relation_export(
        self,
        *,
        export_type: str,
        target_uid: str,
        title: str,
        for_ai_json: Dict[str, Any],
        prompt_text: str,
        external_copy_text: str,
    ) -> None:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO relation_exports (
                    export_type, target_uid, title, for_ai_json, prompt_text, external_copy_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_type,
                    target_uid,
                    title,
                    json.dumps(for_ai_json, ensure_ascii=False),
                    prompt_text,
                    external_copy_text,
                    created_at,
                ),
            )
            connection.commit()

    def get_latest_relation_export(self, export_type: str, target_uid: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT export_type, target_uid, title, for_ai_json, prompt_text, external_copy_text, created_at
                FROM relation_exports
                WHERE export_type = ? AND target_uid = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (export_type, target_uid),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["for_ai_json"] = json.loads(str(payload.get("for_ai_json") or "{}"))
        return payload
