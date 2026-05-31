from __future__ import annotations

from typing import Any, Dict, List

from .prompt_templates import (
    build_friend_external_copy,
    build_friend_prompt_with_json,
    build_self_external_copy,
    build_self_prompt_with_json,
)
from .storage import SiteRepository


class PromptExportService:
    def __init__(self, repository: SiteRepository) -> None:
        self.repository = repository

    @staticmethod
    def _song_payload(row: Dict[str, Any], *, friend_name: str = "") -> Dict[str, Any]:
        direction = str(row.get("direction") or "").strip()
        sender_name = str(row.get("sender_name") or "").strip()
        if direction == "self":
            sender = "我"
            receiver = friend_name or "好友"
            share_direction = "我发给好友"
        elif direction == "friend":
            sender = sender_name or friend_name or "好友"
            receiver = "我"
            share_direction = "好友发给我"
        else:
            sender = sender_name or "未知发送方"
            receiver = "未知接收方"
            share_direction = "未知方向"
        payload = {
            "song_name": row.get("song_name") or "",
            "artist_names": row.get("artist_names") or [],
            "album_name": row.get("album_name") or "",
            "publish_time": row.get("publish_time") or "",
            "genre_label": row.get("genre_label") or "",
            "shared_at": row.get("msg_time_str") or "",
            "sender": sender,
            "receiver": receiver,
            "share_direction": share_direction,
        }
        return payload

    def export_friend_relation(self, uid: str) -> Dict[str, Any]:
        friend = self.repository.get_friend(uid) or {"uid": uid, "nickname": uid}
        all_rows = self.repository.distinct_shared_song_rows(uid)
        known_rows = [row for row in all_rows if str(row.get("genre_status") or "") == "known"]
        unknown_count = len([row for row in all_rows if str(row.get("genre_status") or "") == "unknown"])
        payload = {
            "title": f"与{friend.get('nickname') or uid}的歌曲分享分析",
            "friend_name": friend.get("nickname") or uid,
            "song_count": len(known_rows),
            "songs": [self._song_payload(row, friend_name=friend.get("nickname") or uid) for row in known_rows],
        }
        prompt_text = build_friend_prompt_with_json(payload)
        external_copy = build_friend_external_copy(friend.get("nickname") or uid, len(known_rows), unknown_count)
        self.repository.save_relation_export(
            export_type="friend",
            target_uid=uid,
            title=payload["title"],
            for_ai_json=payload,
            prompt_text=prompt_text,
            external_copy_text=external_copy,
        )
        return {
            "title": payload["title"],
            "for_ai_json": payload,
            "prompt_text": prompt_text,
            "external_copy_text": external_copy,
        }

    def export_self_relation(self) -> Dict[str, Any]:
        friends = self.repository.list_friends()
        friend_map = {row["uid"]: row["nickname"] for row in friends}
        all_rows = self.repository.distinct_all_shared_song_rows()
        known_rows = [row for row in all_rows if str(row.get("genre_status") or "") == "known"]
        unknown_count = len([row for row in all_rows if str(row.get("genre_status") or "") == "unknown"])
        songs: List[Dict[str, Any]] = []
        for row in known_rows:
            friend_name = friend_map.get(str(row.get("uid") or ""), str(row.get("uid") or ""))
            payload = self._song_payload(row, friend_name=friend_name)
            payload["friend_name"] = friend_name
            songs.append(payload)
        export_payload = {
            "title": "我的音乐社交分析",
            "friend_count": len(friends),
            "song_count": len(songs),
            "songs": songs,
        }
        prompt_text = build_self_prompt_with_json(export_payload)
        external_copy = build_self_external_copy(len(friends), len(songs), unknown_count)
        self.repository.save_relation_export(
            export_type="self",
            target_uid="global",
            title=export_payload["title"],
            for_ai_json=export_payload,
            prompt_text=prompt_text,
            external_copy_text=external_copy,
        )
        return {
            "title": export_payload["title"],
            "for_ai_json": export_payload,
            "prompt_text": prompt_text,
            "external_copy_text": external_copy,
        }
