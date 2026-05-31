from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import requests

from .config_store import ConfigStore
from .storage import SiteRepository

MAX_SONG_NAME_LENGTH = 200
MAX_ALBUM_NAME_LENGTH = 200
MAX_ARTIST_COUNT = 10
MAX_ARTIST_NAME_LENGTH = 100
MAX_BATCH_ITEMS = 100
MAX_REQUEST_BYTES = 128 * 1024
DEFAULT_REPEAT_SUPPRESSION_MINUTES = 10
DEFAULT_IP_LIMIT_PER_MINUTE = 20
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1F\x7F]")
MULTI_SPACE_PATTERN = re.compile(r"\s+")
EDGE_PUNCTUATION = " \t\r\n\"'“”‘’`~!@#$%^&*()_+-=[]{}|\\:;,./<>?，。！？、；：（）【】《》"


class RateLimitError(ValueError):
    pass


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def sanitize_text(value: Any, *, max_length: int) -> str:
    text = str(value or "")
    text = CONTROL_CHAR_PATTERN.sub("", text)
    text = MULTI_SPACE_PATTERN.sub(" ", text).strip()
    return text[:max_length]


def normalize_text(value: Any) -> str:
    text = sanitize_text(value, max_length=500)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.strip(EDGE_PUNCTUATION)
    return text


def clean_artist_names(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in list(values or [])[:MAX_ARTIST_COUNT]:
        artist = sanitize_text(value, max_length=MAX_ARTIST_NAME_LENGTH)
        if not artist:
            continue
        normalized = normalize_text(artist)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(artist)
    return result


def build_normalized_key(song_name: Any, artist_names: Iterable[Any], album_name: Any) -> str:
    normalized_artists = sorted(normalize_text(item) for item in artist_names if normalize_text(item))
    return f"{normalize_text(song_name)}::{normalize_text('|'.join(normalized_artists))}::{normalize_text(album_name)}"


def clean_unknown_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    song_name = sanitize_text(payload.get("song_name"), max_length=MAX_SONG_NAME_LENGTH)
    album_name = sanitize_text(payload.get("album_name"), max_length=MAX_ALBUM_NAME_LENGTH)
    artist_names = clean_artist_names(payload.get("artist_names") or [])
    if not song_name:
        raise ValueError("song_name 不能为空。")
    if not artist_names:
        raise ValueError("artist_names 至少需要 1 个歌手。")
    return {
        "song_name": song_name,
        "artist_names": artist_names,
        "album_name": album_name,
        "normalized_key": build_normalized_key(song_name, artist_names, album_name),
    }


class UnknownContributionService:
    def __init__(self, config_store: ConfigStore, repository: SiteRepository) -> None:
        self.config_store = config_store
        self.repository = repository

    def queue_unknown(self, row: Dict[str, Any]) -> None:
        cleaned = clean_unknown_item(row)
        self.repository.upsert_pending_unknown_upload(cleaned)

    def backfill_pending_from_local_unknowns(self) -> Dict[str, Any]:
        candidates = self.repository.list_distinct_unknown_song_candidates()
        queued_count = 0
        for row in candidates:
            try:
                self.queue_unknown(row)
                queued_count += 1
            except ValueError:
                continue
        return {"ok": True, "queued_count": queued_count}

    def get_privacy_settings(self) -> Dict[str, Any]:
        payload = self.config_store.load()
        return {
            "allow_unknown_song_contribution": bool(payload.get("allow_unknown_song_contribution", False)),
            "description": "开启后，Shadow 会在遇到无法识别的歌曲时，仅上传该歌曲的歌名、歌手、专辑，用于完善公共歌曲映射数据。不会上传网易云 cookie、聊天记录、好友 UID、私信原文或完整歌单。",
            "queue_summary": self.repository.get_pending_unknown_upload_stats(),
        }

    def update_privacy_settings(self, allow_unknown_song_contribution: bool) -> Dict[str, Any]:
        next_value = bool(allow_unknown_song_contribution)
        self.config_store.update(allow_unknown_song_contribution=next_value)
        if next_value:
            self.backfill_pending_from_local_unknowns()
        return self.get_privacy_settings()

    def flush_pending_uploads(self, batch_size: int = 50) -> Dict[str, Any]:
        settings = self.config_store.load()
        if not bool(settings.get("allow_unknown_song_contribution", False)):
            return {"ok": False, "uploaded": 0, "reason": "contribution_disabled"}
        submit_url = str(settings.get("unknown_song_submit_url") or "").strip()
        if not submit_url:
            return {"ok": False, "uploaded": 0, "reason": "submit_url_missing"}

        rows = self.repository.list_pending_unknown_uploads(statuses=["pending", "failed"], limit=min(batch_size, MAX_BATCH_ITEMS))
        if not rows:
            return {"ok": True, "uploaded": 0, "reason": "no_pending_items"}

        items = [
            {
                "song_name": row["song_name"],
                "artist_names": row["artist_names"],
                "album_name": row["album_name"],
            }
            for row in rows
        ]
        body = {"items": items, "client_version": "shadow_music_site/local"}
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            rows = rows[:20]
            items = items[:20]
            body = {"items": items, "client_version": "shadow_music_site/local"}

        response = requests.post(submit_url, json=body, timeout=10)
        if response.status_code >= 400:
            self.repository.mark_pending_unknown_uploads_failed([int(row["id"]) for row in rows])
            raise RuntimeError(f"unknown 上传失败：HTTP {response.status_code}")

        self.repository.mark_pending_unknown_uploads_uploaded([int(row["id"]) for row in rows])
        return {"ok": True, "uploaded": len(rows), "reason": "uploaded"}

    def flush_pending_uploads_quietly(self, batch_size: int = 50) -> Dict[str, Any]:
        try:
            return self.flush_pending_uploads(batch_size=batch_size)
        except Exception:
            return {"ok": False, "uploaded": 0, "reason": "flush_failed"}

    def handle_batch_submit(self, payload: Dict[str, Any], client_ip: str) -> Tuple[int, Dict[str, Any]]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("items 必须是数组。")
        if len(items) > MAX_BATCH_ITEMS:
            raise ValueError(f"单次最多提交 {MAX_BATCH_ITEMS} 条。")
        raw_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if raw_size > MAX_REQUEST_BYTES:
            raise ValueError("请求体过大。")
        try:
            self.repository.enforce_unknown_submit_rate_limit(client_ip=client_ip, limit_per_minute=DEFAULT_IP_LIMIT_PER_MINUTE)
        except ValueError as exc:
            raise RateLimitError(str(exc)) from exc

        deduped: Dict[str, Dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                cleaned = clean_unknown_item(item)
            except ValueError:
                continue
            deduped.setdefault(cleaned["normalized_key"], cleaned)

        inserted_count = 0
        incremented_count = 0
        suppressed_count = 0
        now = _now_text()
        cutoff = datetime.now() - timedelta(minutes=DEFAULT_REPEAT_SUPPRESSION_MINUTES)
        for row in deduped.values():
            existing = self.repository.get_unknown_song_submission_by_key(row["normalized_key"])
            if not existing:
                self.repository.insert_unknown_song_submission(row, now=now)
                inserted_count += 1
                continue
            last_submitted_at = _parse_time(existing.get("last_submitted_at"))
            if last_submitted_at and last_submitted_at >= cutoff:
                self.repository.touch_unknown_song_submission(row["normalized_key"], now=now, increment_submit_count=False)
                suppressed_count += 1
                continue
            self.repository.touch_unknown_song_submission(row["normalized_key"], now=now, increment_submit_count=True)
            incremented_count += 1

        return 200, {
            "ok": True,
            "received_count": len(items),
            "batch_deduped_count": len(deduped),
            "accepted_count": len(deduped),
            "inserted_count": inserted_count,
            "submit_count_incremented": incremented_count,
            "suppressed_count": suppressed_count,
        }

    def _require_admin_token(self, provided_token: str) -> None:
        expected = str(self.config_store.load().get("unknown_song_admin_token") or "").strip()
        if not expected or provided_token.strip() != expected:
            raise PermissionError("管理员令牌无效。")

    def export_unknown_songs(self, provided_token: str, *, status: str = "pending") -> List[Dict[str, Any]]:
        self._require_admin_token(provided_token)
        rows = self.repository.list_unknown_song_submissions(status=status if status != "all" else None)
        return [
            {
                "song_name": row["song_name"],
                "artist_names": row["artist_names"],
                "album_name": row["album_name"],
            }
            for row in rows
        ]

    def get_admin_stats(self, provided_token: str) -> Dict[str, Any]:
        self._require_admin_token(provided_token)
        return self.repository.get_unknown_song_submission_stats()

    def get_top_unknown_songs(self, provided_token: str, limit: int = 100) -> List[Dict[str, Any]]:
        self._require_admin_token(provided_token)
        return self.repository.list_top_unknown_song_submissions(limit=limit)

    def mark_exported(self, provided_token: str, *, status: str = "pending") -> Dict[str, Any]:
        self._require_admin_token(provided_token)
        count = self.repository.update_unknown_song_submission_status(from_status=status if status != "all" else None, to_status="exported")
        return {"ok": True, "updated_count": count}

    def ignore_unknown_keys(self, provided_token: str, keys: List[str]) -> Dict[str, Any]:
        self._require_admin_token(provided_token)
        count = self.repository.update_unknown_song_submission_status_by_keys(keys=keys, to_status="ignored")
        return {"ok": True, "updated_count": count}

    def cleanup_exported(self, provided_token: str) -> Dict[str, Any]:
        self._require_admin_token(provided_token)
        count = self.repository.delete_unknown_song_submissions_by_status("exported")
        return {"ok": True, "deleted_count": count}
