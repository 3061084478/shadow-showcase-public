from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List

from .friend_directory import FriendDirectoryService
from .message_archive import MessageArchiveService
from .storage import SiteRepository


class InitialSyncService:
    def __init__(
        self,
        friend_directory: FriendDirectoryService,
        message_archive: MessageArchiveService,
        repository: SiteRepository,
        genre_retagger: Any | None = None,
    ) -> None:
        self.friend_directory = friend_directory
        self.message_archive = message_archive
        self.repository = repository
        self.genre_retagger = genre_retagger
        self._lock = threading.Lock()
        self._status: Dict[str, Any] = self._empty_status()

    @staticmethod
    def _empty_status() -> Dict[str, Any]:
        return {
            "running": False,
            "finished": False,
            "total_friends": 0,
            "completed_friends": 0,
            "current_friend_uid": "",
            "current_friend_name": "",
            "succeeded": 0,
            "failed": 0,
            "errors": [],
            "started_at": "",
            "finished_at": "",
            "delta_message_count": 0,
            "delta_song_count": 0,
            "current_delta_message_count": 0,
            "current_delta_song_count": 0,
            "last_friend_result": None,
        }

    def _snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._status,
                "errors": list(self._status.get("errors") or []),
            }

    def status(self) -> Dict[str, Any]:
        return self._snapshot()

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._status["running"]:
                return {
                    **self._status,
                    "errors": list(self._status.get("errors") or []),
                }
            self._status = {
                **self._empty_status(),
                "running": True,
                "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return self._snapshot()

    def _set_current_friend(self, uid: str, nickname: str) -> None:
        with self._lock:
            self._status["current_friend_uid"] = uid
            self._status["current_friend_name"] = nickname

    def _mark_progress(
        self,
        *,
        succeeded: bool,
        error_message: str = "",
        delta_message_count: int = 0,
        delta_song_count: int = 0,
    ) -> None:
        with self._lock:
            self._status["completed_friends"] += 1
            self._status["delta_message_count"] += int(delta_message_count or 0)
            self._status["delta_song_count"] += int(delta_song_count or 0)
            self._status["current_delta_message_count"] = int(delta_message_count or 0)
            self._status["current_delta_song_count"] = int(delta_song_count or 0)
            self._status["last_friend_result"] = {
                "friend_uid": str(self._status.get("current_friend_uid") or ""),
                "friend_name": str(self._status.get("current_friend_name") or ""),
                "delta_message_count": int(delta_message_count or 0),
                "delta_song_count": int(delta_song_count or 0),
                "status": "ok" if succeeded else "error",
                "error": error_message,
            }
            if succeeded:
                self._status["succeeded"] += 1
            else:
                self._status["failed"] += 1
                if error_message:
                    errors: List[Dict[str, str]] = self._status.setdefault("errors", [])
                    errors.append(
                        {
                            "friend_uid": str(self._status.get("current_friend_uid") or ""),
                            "friend_name": str(self._status.get("current_friend_name") or ""),
                            "error": error_message,
                        }
                    )

    def _finish(self) -> None:
        with self._lock:
            self._status["running"] = False
            self._status["finished"] = True
            self._status["current_friend_uid"] = ""
            self._status["current_friend_name"] = ""
            self._status["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _resolve_sync_friends(self, sync_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        mutual_friends = sync_result.get("mutual_friends")
        if isinstance(mutual_friends, list):
            return mutual_friends
        repository_friends = self.repository.list_friends()
        if isinstance(repository_friends, list):
            return repository_friends
        return []

    def _reindex_unknown_quietly(self) -> Dict[str, Any]:
        if self.genre_retagger is None:
            return {"triggered": False, "reason": "genre_retagger_missing"}
        try:
            return {
                "triggered": True,
                "result": self.genre_retagger.reindex_unknown(),
            }
        except Exception as exc:
            return {
                "triggered": False,
                "reason": "reindex_unknown_failed",
                "error": str(exc),
            }

    def _run(self) -> None:
        try:
            sync_result = self.friend_directory.sync_friends()
            friends = self._resolve_sync_friends(sync_result)
            with self._lock:
                self._status["total_friends"] = len(friends)

            for friend in friends:
                uid = str(friend.get("uid") or "").strip()
                if not uid:
                    continue
                nickname = str(friend.get("nickname") or "").strip()
                self._set_current_friend(uid, nickname)
                try:
                    result: Dict[str, Any]
                    backfill_status = self.repository.get_backfill_status(uid)
                    if backfill_status is None:
                        result = self.message_archive.sync_full_history_backfill(uid, limit=50)
                    else:
                        latest_archived = self.repository.get_latest_message(uid)
                        stop_at_ms = int((latest_archived or {}).get("msg_time_ms") or 0)
                        if stop_at_ms <= 0:
                            result = self.message_archive.sync_full_history_backfill(uid, limit=50)
                        else:
                            result = self.message_archive.sync_recent_history_delta(uid, initial_pages=6, limit=50, stop_at_ms=stop_at_ms)
                    self._mark_progress(
                        succeeded=True,
                        delta_message_count=int(result.get("inserted_count") or 0),
                        delta_song_count=int(result.get("inserted_song_count") or 0),
                    )
                except Exception as exc:
                    self._mark_progress(succeeded=False, error_message=str(exc))
        except Exception as exc:
            with self._lock:
                self._status["failed"] += 1
                errors: List[Dict[str, str]] = self._status.setdefault("errors", [])
                errors.append(
                    {
                        "friend_uid": "",
                        "friend_name": "",
                        "error": str(exc),
                    }
                )
        finally:
            reindex_result = self._reindex_unknown_quietly()
            with self._lock:
                self._status["unknown_reindex"] = reindex_result
            self._finish()

    def archive_all_from_cursors(self, initial_pages: int = 1, limit: int = 50) -> Dict[str, Any]:
        sync_result = self.friend_directory.sync_friends()
        friends = self._resolve_sync_friends(sync_result)
        full_synced = 0
        delta_synced = 0
        failed: List[Dict[str, str]] = []
        for friend in friends:
            uid = str(friend.get("uid") or "").strip()
            if not uid:
                continue
            try:
                backfill_status = self.repository.get_backfill_status(uid)
                if backfill_status is None:
                    self.message_archive.sync_full_history_backfill(uid=uid, limit=limit)
                    full_synced += 1
                    continue
                latest_archived = self.repository.get_latest_message(uid=uid)
                stop_at_ms = int((latest_archived or {}).get("msg_time_ms") or 0)
                if stop_at_ms <= 0:
                    self.message_archive.sync_full_history_backfill(uid=uid, limit=limit)
                    full_synced += 1
                else:
                    self.message_archive.sync_recent_history_delta(
                        uid=uid,
                        initial_pages=initial_pages,
                        limit=limit,
                        stop_at_ms=stop_at_ms,
                    )
                    delta_synced += 1
            except Exception as exc:
                failed.append(
                    {
                        "uid": uid,
                        "name": str(friend.get("nickname") or friend.get("friend_name") or uid),
                        "error": str(exc),
                    }
                )
        unknown_reindex = self._reindex_unknown_quietly()
        return {
            "friends": friends,
            "total_friends": len(friends),
            "full_synced": full_synced,
            "delta_synced": delta_synced,
            "failed": failed,
            "skipped": False,
            "unknown_reindex": unknown_reindex,
        }

    def rebuild_all_full(self, limit: int = 50) -> Dict[str, Any]:
        sync_result = self.friend_directory.sync_friends()
        friends = self._resolve_sync_friends(sync_result)
        succeeded = 0
        failed: List[Dict[str, str]] = []
        for friend in friends:
            uid = str(friend.get("uid") or "").strip()
            if not uid:
                continue
            try:
                self.message_archive.sync_full_history_backfill(uid=uid, limit=limit)
                succeeded += 1
            except Exception as exc:
                failed.append(
                    {
                        "uid": uid,
                        "name": str(friend.get("nickname") or friend.get("friend_name") or uid),
                        "error": str(exc),
                    }
                )
        unknown_reindex = self._reindex_unknown_quietly()
        return {
            "friends": friends,
            "total_friends": len(friends),
            "full_synced": succeeded,
            "delta_synced": 0,
            "failed": failed,
            "skipped": False,
            "unknown_reindex": unknown_reindex,
        }
