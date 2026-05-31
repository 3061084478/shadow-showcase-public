from __future__ import annotations

from typing import Any, Dict, List

from .storage import SiteRepository


class ChatQueryService:
    CHAT_QUERY_SCOPE = "chat_query"

    @staticmethod
    def _window_limit_from_pages(pages: int) -> int:
        safe_pages = max(1, int(pages or 1))
        return safe_pages * 30

    def __init__(self, repository: SiteRepository) -> None:
        self.repository = repository

    @staticmethod
    def _paginate(rows: List[Dict[str, Any]], page: int, limit: int) -> Dict[str, Any]:
        safe_page = max(1, int(page or 1))
        safe_limit = max(1, min(500, int(limit or 50)))
        start = (safe_page - 1) * safe_limit
        end = start + safe_limit
        return {
            "page": safe_page,
            "limit": safe_limit,
            "total": len(rows),
            "rows": rows[start:end],
        }

    @staticmethod
    def _slice_recent(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(500, int(limit or 50)))
        if len(rows) <= safe_limit:
            return rows
        return rows[-safe_limit:]

    @staticmethod
    def _filter_incremental_rows(
        rows: List[Dict[str, Any]],
        state: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        start_ms = int((state or {}).get("last_consumed_msg_time_ms") or 0)
        start_msg_id = str((state or {}).get("last_consumed_msg_id") or "")
        return [
            row
            for row in rows
            if (int(row.get("msg_time_ms") or 0), str(row.get("msg_id") or "")) > (start_ms, start_msg_id)
        ]

    def _advance_query_state(self, uid: str, feature_scope: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        latest = max(rows, key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")))
        self.repository.advance_consumption_state(
            uid=uid,
            feature_scope=feature_scope,
            last_consumed_msg_id=str(latest.get("msg_id") or ""),
            last_consumed_msg_time_ms=int(latest.get("msg_time_ms") or 0),
            last_consumed_msg_time_str=str(latest.get("msg_time_str") or ""),
        )

    def query(self, uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope = str(payload.get("scope") or "all").strip().lower()
        sender_scope = str(payload.get("sender_scope") or "all").strip().lower()
        msg_type = str(payload.get("msg_type") or "all").strip().lower()
        keyword = str(payload.get("keyword") or "").strip() or None
        date = str(payload.get("date") or "").strip()
        start_date = str(payload.get("start_date") or "").strip()
        end_date = str(payload.get("end_date") or "").strip()
        page_payload = payload.get("page")
        limit_payload = payload.get("limit")
        explicit_page = page_payload is not None and str(page_payload).strip() != ""
        explicit_limit = limit_payload is not None and str(limit_payload).strip() != ""
        page = int(page_payload or 1)
        limit = int(limit_payload or 50)

        start_datetime = f"{date} 00:00:00" if date else (f"{start_date} 00:00:00" if start_date else None)
        end_datetime = f"{date} 23:59:59" if date else (f"{end_date} 23:59:59" if end_date else None)
        rows = self.repository.query_raw_messages(
            uid,
            direction=sender_scope,
            msg_type=msg_type,
            keyword=keyword,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        enriched_song_map = {
            str(row.get("msg_id") or ""): row
            for row in self.repository.query_shared_song_messages(uid)
        }
        merged_rows: List[Dict[str, Any]] = []
        for row in rows:
            merged = dict(row)
            linked_song = enriched_song_map.get(str(row.get("msg_id") or ""))
            if linked_song:
                merged.update(
                    {
                        "artist_names": linked_song.get("artist_names") or [],
                        "album_id": linked_song.get("album_id") or "",
                        "album_name": linked_song.get("album_name") or "",
                        "publish_time": linked_song.get("publish_time") or "",
                        "genre_label": linked_song.get("genre_label") or "",
                        "genre_status": linked_song.get("genre_status") or "",
                    }
                )
            merged_rows.append(merged)
        merged_rows.sort(key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")))

        if scope == "recent":
            merged_rows = self._slice_recent(merged_rows, limit)
            return {"scope": scope, "total": len(merged_rows), "rows": merged_rows}
        if scope == "incremental":
            state = self.repository.get_consumption_state(uid, self.CHAT_QUERY_SCOPE)
            merged_rows = self._filter_incremental_rows(merged_rows, state)
            returned_rows = self._slice_recent(merged_rows, limit)
            self._advance_query_state(uid, self.CHAT_QUERY_SCOPE, returned_rows)
            return {"scope": scope, "total": len(merged_rows), "rows": returned_rows}
        if scope == "pages":
            window_rows = self._slice_recent(merged_rows, self._window_limit_from_pages(page))
            return {"scope": scope, "total": len(window_rows), "rows": window_rows}
        if scope == "all" and not explicit_page and not explicit_limit:
            return {"scope": scope, "total": len(merged_rows), "rows": merged_rows}
        result = self._paginate(merged_rows, page, limit)
        result["scope"] = scope
        return result

    def active_dates(self, uid: str) -> List[str]:
        return self.repository.list_raw_message_active_dates(uid)

    def query_shared_songs(self, uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope = str(payload.get("scope") or "all").strip().lower()
        sender_scope = str(payload.get("sender_scope") or "all").strip().lower()
        keyword = str(payload.get("keyword") or "").strip() or None
        known_only = bool(payload.get("known_only", False))
        date = str(payload.get("date") or "").strip()
        start_date = str(payload.get("start_date") or "").strip()
        end_date = str(payload.get("end_date") or "").strip()
        page_payload = payload.get("page")
        limit_payload = payload.get("limit")
        explicit_page = page_payload is not None and str(page_payload).strip() != ""
        explicit_limit = limit_payload is not None and str(limit_payload).strip() != ""
        page = int(page_payload or 1)
        limit = int(limit_payload or 50)

        start_datetime = f"{date} 00:00:00" if date else (f"{start_date} 00:00:00" if start_date else None)
        end_datetime = f"{date} 23:59:59" if date else (f"{end_date} 23:59:59" if end_date else None)
        rows = self.repository.query_shared_song_messages(
            uid,
            direction=sender_scope,
            keyword=keyword,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            known_only=known_only,
        )
        rows.sort(key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")))

        if scope == "recent":
            rows = self._slice_recent(rows, limit)
            return {"scope": scope, "total": len(rows), "rows": rows}
        if scope == "incremental":
            state = self.repository.get_consumption_state(uid, self.CHAT_QUERY_SCOPE)
            rows = self._filter_incremental_rows(rows, state)
            returned_rows = self._slice_recent(rows, limit)
            self._advance_query_state(uid, self.CHAT_QUERY_SCOPE, returned_rows)
            return {"scope": scope, "total": len(rows), "rows": returned_rows}

        if scope == "all" and not explicit_page and not explicit_limit:
            return {"scope": scope, "total": len(rows), "rows": rows}
        result = self._paginate(rows, page, limit)
        result["scope"] = scope
        return result

    def shared_song_active_dates(self, uid: str) -> List[str]:
        return self.repository.list_shared_song_active_dates(uid)
