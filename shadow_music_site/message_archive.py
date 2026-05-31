from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .netease_api import NeteaseApiClient
from .unknown_contribution import UnknownContributionService
from .parser import parse_chat_messages, parse_song_messages
from .song_enrichment import SongEnrichmentService
from .storage import SiteRepository


class MessageArchiveService:
    PLAYLIST_GENERATION_FEATURE_SCOPE = "chat_query_song"
    CHAT_QUERY_FEATURE_SCOPE = "chat_query"
    CHAT_ARCHIVE_CURSOR_SCOPE = "chat_archive_cursor"
    SONG_ARCHIVE_CURSOR_SCOPE = "song_archive_cursor"

    def __init__(
        self,
        api_client: NeteaseApiClient,
        repository: SiteRepository,
        enrichment_service: SongEnrichmentService,
        unknown_contribution: UnknownContributionService,
    ) -> None:
        self.api_client = api_client
        self.repository = repository
        self.enrichment_service = enrichment_service
        self.unknown_contribution = unknown_contribution

    def _fetch_all_private_history(self, uid: str, page_size: int = 200) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        before: int | None = None
        while True:
            page = self.api_client.get_private_messages_for_archive(uid=uid, limit=page_size, before=before)
            if not page:
                break
            added_count = 0
            min_time = None
            for item in page:
                msg_id = str(item.get("id") or item.get("msgId") or "").strip()
                dedupe_key = msg_id or f"{item.get('time')}::{item.get('fromUserId')}"
                if dedupe_key in seen_ids:
                    continue
                seen_ids.add(dedupe_key)
                all_rows.append(item)
                added_count += 1
                msg_time = item.get("time")
                if isinstance(msg_time, int):
                    min_time = msg_time if min_time is None else min(min_time, msg_time)
            if added_count == 0 or len(page) < page_size:
                break
            if min_time is None or min_time <= 0:
                break
            before = int(min_time - 1)
        all_rows.sort(key=lambda item: int(item.get("time") or 0))
        return all_rows

    def get_archive_summary(self, uid: str) -> Dict[str, Any]:
        summary = self.repository.get_archive_range(uid)
        summary["active_dates"] = self.repository.list_raw_message_active_dates(uid)
        summary["backfill_status"] = self.repository.get_backfill_status(uid)
        latest_message = self.repository.get_latest_message(uid)
        summary["last_message_at"] = latest_message.get("msg_time_str") if latest_message else None
        summary["message_count"] = self.repository.count_raw_messages(uid)
        summary["shared_song_count"] = self.repository.count_distinct_shared_songs(uid)
        summary["known_song_count"] = self.repository.count_distinct_shared_songs(uid, known_only=True)
        summary["unknown_song_count"] = self.repository.count_distinct_shared_songs(uid, unknown_only=True)
        return summary

    @staticmethod
    def _resolve_window_message_limit(pages: int) -> int:
        if pages < 1:
            raise ValueError("消息窗口页数必须大于等于 1。")
        return pages * 30

    def _get_archived_window_messages(self, uid: str, pages: int) -> List[Dict[str, Any]]:
        all_messages = self.repository.query_raw_messages(uid=uid)
        if not all_messages:
            return []
        message_limit = self._resolve_window_message_limit(pages)
        return all_messages[-message_limit:]

    def _get_incremental_messages_from_archive(self, uid: str) -> List[Dict[str, Any]]:
        consumption_state = self.repository.get_consumption_state(uid=uid, feature_scope=self.CHAT_QUERY_FEATURE_SCOPE)
        start_datetime = None
        start_time_ms = 0
        last_consumed_msg_id = ""
        if consumption_state:
            start_datetime = consumption_state.get("last_consumed_msg_time_str") or None
            start_time_ms = int(consumption_state.get("last_consumed_msg_time_ms") or 0)
            last_consumed_msg_id = str(consumption_state.get("last_consumed_msg_id") or "")
        rows = self.repository.query_raw_messages(uid=uid, start_datetime=start_datetime)
        result = []
        for item in rows:
            item_time_ms = int(item.get("msg_time_ms") or 0)
            item_msg_id = str(item.get("msg_id") or "")
            if item_time_ms < start_time_ms:
                continue
            if item_time_ms == start_time_ms and last_consumed_msg_id and item_msg_id <= last_consumed_msg_id:
                continue
            result.append(item)
        return result

    def _mark_messages_consumed(self, uid: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        latest_message = max(rows, key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")))
        self.repository.advance_consumption_state(
            uid=uid,
            feature_scope=self.CHAT_QUERY_FEATURE_SCOPE,
            last_consumed_msg_id=str(latest_message.get("msg_id") or ""),
            last_consumed_msg_time_ms=int(latest_message.get("msg_time_ms") or 0),
            last_consumed_msg_time_str=str(latest_message.get("msg_time_str") or ""),
        )

    def advance_chat_archive_cursor(self, uid: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        latest_message = max(rows, key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")))
        self.repository.advance_consumption_state(
            uid=uid,
            feature_scope=self.CHAT_ARCHIVE_CURSOR_SCOPE,
            last_consumed_msg_id=str(latest_message.get("msg_id") or ""),
            last_consumed_msg_time_ms=int(latest_message.get("msg_time_ms") or 0),
            last_consumed_msg_time_str=str(latest_message.get("msg_time_str") or ""),
        )

    def sync_chat_archive_cursor_to_latest_archived(self, uid: str) -> None:
        latest_message = self.repository.get_latest_message(uid=uid)
        if not latest_message:
            return
        self.repository.advance_consumption_state(
            uid=uid,
            feature_scope=self.CHAT_ARCHIVE_CURSOR_SCOPE,
            last_consumed_msg_id=str(latest_message.get("msg_id") or ""),
            last_consumed_msg_time_ms=int(latest_message.get("msg_time_ms") or 0),
            last_consumed_msg_time_str=str(latest_message.get("msg_time_str") or ""),
        )

    def get_chat_archive_cursor_ms(self, uid: str) -> int:
        state = self.repository.get_consumption_state(uid=uid, feature_scope=self.CHAT_ARCHIVE_CURSOR_SCOPE)
        return int((state or {}).get("last_consumed_msg_time_ms") or 0)

    def sync_recent_history_delta(self, uid: str, initial_pages: int = 3, limit: int = 50, stop_at_ms: int | None = None) -> Dict[str, Any]:
        archive_range_before = self.repository.get_archive_range(uid)
        previous_newest = archive_range_before.get("newest_archived_time")
        previous_newest_ms = None
        if previous_newest:
            previous_newest_ms = int(datetime.strptime(previous_newest, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
        if stop_at_ms is not None:
            previous_newest_ms = max(previous_newest_ms or 0, int(stop_at_ms or 0))

        request_limit = min(limit, 50) if limit > 0 else 50
        target_message_count = self._resolve_window_message_limit(initial_pages)
        collected_message_count = 0
        total_processed = 0
        total_inserted = 0
        total_skipped = 0
        fetched_pages = 0
        inserted_song_count = 0
        known_song_count_delta = 0
        unknown_song_count_delta = 0
        before: int | None = None
        previous_page_signature: tuple[str, ...] | None = None

        while True:
            raw_messages = self.api_client.get_private_messages_for_archive(uid=uid, limit=request_limit, before=before)
            if not raw_messages:
                break
            page_signature = tuple(str(item.get("id") or item.get("msgId") or "") for item in raw_messages)
            if previous_page_signature is not None and page_signature == previous_page_signature:
                break
            previous_page_signature = page_signature
            parsed_messages = parse_chat_messages(raw_messages, uid=uid)
            song_rows = parse_song_messages(raw_messages, uid=uid)
            enriched_song_rows = self.enrichment_service.enrich_songs(song_rows)
            write_result = self.repository.upsert_raw_messages(parsed_messages)
            for row in enriched_song_rows:
                was_inserted = self.repository.upsert_shared_song_message(row)
                if not was_inserted:
                    continue
                inserted_song_count += 1
                if str(row.get("genre_status") or "") == "unknown":
                    unknown_song_count_delta += 1
                    self.repository.upsert_unknown(
                        {
                            "source_friend_uid": uid,
                            "source_friend_name": row.get("sender_name") or "",
                            "msg_id": row.get("msg_id") or "",
                            "song_id": row.get("song_id") or "",
                            "song_name": row.get("song_name") or "",
                            "artist_names": row.get("artist_names") or [],
                            "album_name": row.get("album_name") or "",
                        }
                    )
                    self.unknown_contribution.queue_unknown(
                        {
                            "song_name": row.get("song_name") or "",
                            "artist_names": row.get("artist_names") or [],
                            "album_name": row.get("album_name") or "",
                        }
                    )
                else:
                    known_song_count_delta += 1
            fetched_pages += 1
            total_processed += len(parsed_messages)
            total_inserted += write_result
            total_skipped += len(parsed_messages) - write_result
            collected_message_count += len(raw_messages)
            sorted_messages = sorted(raw_messages, key=lambda item: int(item.get("time", 0)))
            page_earliest_ms = int(sorted_messages[0].get("time", 0))
            if previous_newest_ms is not None and page_earliest_ms <= previous_newest_ms:
                break
            before = max(0, page_earliest_ms - 1)
            if previous_newest_ms is None and collected_message_count >= target_message_count:
                break

        summary = self.get_archive_summary(uid)
        summary.update(
            {
                "processed_count": total_processed,
                "inserted_count": total_inserted,
                "skipped_count": total_skipped,
                "pages_fetched": fetched_pages,
                "inserted_song_count": inserted_song_count,
                "known_song_count_delta": known_song_count_delta,
                "unknown_song_count_delta": unknown_song_count_delta,
                "available_range_notice": "当前结果来自本地归档，可继续刷新获取最新增量。",
            }
        )
        self.unknown_contribution.flush_pending_uploads_quietly()
        return summary

    def sync_full_history_backfill(self, uid: str, limit: int = 50) -> Dict[str, Any]:
        request_limit = min(limit, 50) if limit > 0 else 50
        fetched_pages = 0
        total_processed = 0
        total_inserted = 0
        total_skipped = 0
        total_song_inserted = 0
        total_known_song_count = 0
        total_unknown_song_count = 0
        before: int | None = None
        previous_page_signature: tuple[str, ...] | None = None

        while True:
            raw_messages = self.api_client.get_private_messages_for_archive(uid=uid, limit=request_limit, before=before)
            if not raw_messages:
                break

            page_signature = tuple(str(item.get("id") or item.get("msgId") or "") for item in raw_messages)
            if previous_page_signature is not None and page_signature == previous_page_signature:
                break
            previous_page_signature = page_signature

            parsed_messages = parse_chat_messages(raw_messages, uid=uid)
            song_rows = parse_song_messages(raw_messages, uid=uid)
            enriched_song_rows = self.enrichment_service.enrich_songs(song_rows)
            write_result = self.repository.upsert_raw_messages(parsed_messages)
            for row in enriched_song_rows:
                was_inserted = self.repository.upsert_shared_song_message(row)
                if not was_inserted:
                    continue
                total_song_inserted += 1
                if str(row.get("genre_status") or "") == "unknown":
                    total_unknown_song_count += 1
                    self.repository.upsert_unknown(
                        {
                            "source_friend_uid": uid,
                            "source_friend_name": row.get("sender_name") or "",
                            "msg_id": row.get("msg_id") or "",
                            "song_id": row.get("song_id") or "",
                            "song_name": row.get("song_name") or "",
                            "artist_names": row.get("artist_names") or [],
                            "album_name": row.get("album_name") or "",
                        }
                    )
                    self.unknown_contribution.queue_unknown(
                        {
                            "song_name": row.get("song_name") or "",
                            "artist_names": row.get("artist_names") or [],
                            "album_name": row.get("album_name") or "",
                        }
                    )
                else:
                    total_known_song_count += 1
            fetched_pages += 1
            total_processed += len(parsed_messages)
            total_inserted += write_result
            total_skipped += len(parsed_messages) - write_result

            sorted_messages = sorted(raw_messages, key=lambda item: int(item.get("time", 0)))
            earliest_time_ms = int(sorted_messages[0].get("time", 0))
            next_before = max(0, earliest_time_ms - 1)
            if before is not None and next_before >= before:
                break
            before = next_before

        archive_range = self.repository.get_archive_range(uid)
        self.repository.save_backfill_status(
            uid=uid,
            status="completed",
            pages_fetched=fetched_pages,
            fetched_count=total_processed,
            inserted_count=total_inserted,
            oldest_archived_time=archive_range.get("oldest_archived_time"),
            newest_archived_time=archive_range.get("newest_archived_time"),
        )
        summary = self.get_archive_summary(uid)
        summary.update(
            {
                "processed_count": total_processed,
                "inserted_count": total_inserted,
                "skipped_count": total_skipped,
                "pages_fetched": fetched_pages,
                "inserted_song_count": total_song_inserted,
                "known_song_count_delta": total_known_song_count,
                "unknown_song_count_delta": total_unknown_song_count,
                "available_range_notice": "当前结果来自完整本地归档，后续会自动追加最新增量。",
            }
        )
        self.unknown_contribution.flush_pending_uploads_quietly()
        return summary

    def rebuild_friend_archive(self, uid: str) -> Dict[str, Any]:
        raw_msgs = self._fetch_all_private_history(uid)
        chat_rows = parse_chat_messages(raw_msgs, uid)
        song_rows = parse_song_messages(raw_msgs, uid)
        enriched_song_rows = self.enrichment_service.enrich_songs(song_rows)

        self.repository.delete_friend_archive(uid)
        raw_count = self.repository.upsert_raw_messages(chat_rows)
        for row in enriched_song_rows:
            self.repository.upsert_shared_song_message(row)
            if str(row.get("genre_status") or "") == "unknown":
                self.repository.upsert_unknown(
                    {
                        "source_friend_uid": uid,
                        "source_friend_name": row.get("sender_name") or "",
                        "msg_id": row.get("msg_id") or "",
                        "song_id": row.get("song_id") or "",
                        "song_name": row.get("song_name") or "",
                        "artist_names": row.get("artist_names") or [],
                        "album_name": row.get("album_name") or "",
                    }
                )
                self.unknown_contribution.queue_unknown(
                    {
                        "song_name": row.get("song_name") or "",
                        "artist_names": row.get("artist_names") or [],
                        "album_name": row.get("album_name") or "",
                    }
                )

        unknown_count = sum(1 for row in enriched_song_rows if str(row.get("genre_status") or "") == "unknown")
        distinct_summary = self.get_archive_summary(uid)
        archive_range = self.repository.get_archive_range(uid)
        self.repository.save_backfill_status(
            uid=uid,
            status="completed",
            pages_fetched=0,
            fetched_count=len(chat_rows),
            inserted_count=raw_count,
            oldest_archived_time=archive_range.get("oldest_archived_time"),
            newest_archived_time=archive_range.get("newest_archived_time"),
        )
        self.unknown_contribution.flush_pending_uploads_quietly()
        return {
            "uid": uid,
            "raw_message_count": raw_count,
            "shared_song_count": distinct_summary.get("shared_song_count", 0),
            "known_song_count": distinct_summary.get("known_song_count", 0),
            "unknown_song_count": distinct_summary.get("unknown_song_count", 0),
            "archive_range": distinct_summary,
        }
