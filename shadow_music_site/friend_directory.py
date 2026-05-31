from __future__ import annotations

from typing import Any, Dict, List

from .bootstrap import StartupBootstrap
from .storage import SiteRepository


class FriendDirectoryService:
    def __init__(self, bootstrap: StartupBootstrap, repository: SiteRepository) -> None:
        self.bootstrap = bootstrap
        self.repository = repository

    def _current_user_id(self) -> str:
        status = self.bootstrap.ensure_authenticated()
        uid = str(status.get("user_id") or "").strip()
        if not uid:
            raise RuntimeError("当前登录态缺少用户 ID，无法同步好友。")
        return uid

    @staticmethod
    def _normalize_user_row(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "uid": str(raw.get("userId") or raw.get("uid") or "").strip(),
            "nickname": str(raw.get("nickname") or raw.get("remarkName") or raw.get("userName") or "").strip() or "未命名好友",
            "avatar_url": str(raw.get("avatarUrl") or raw.get("avatar") or "").strip(),
        }

    def _collect_all_pages(self, fn_name: str, uid: str) -> List[Dict[str, Any]]:
        api = self.bootstrap.api_client
        rows: List[Dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            if fn_name == "follows":
                page = api.get_user_follows_page(uid=uid, limit=limit, offset=offset)
            else:
                page = api.get_user_followeds_page(uid=uid, limit=limit, offset=offset)
            users = page.get("users") or []
            if not users:
                break
            rows.extend(users)
            if not page.get("more"):
                break
            offset += limit
        return rows

    def sync_friends(self) -> Dict[str, Any]:
        self.bootstrap.ensure_api_ready()
        uid = self._current_user_id()
        follows = self._collect_all_pages("follows", uid)
        followeds = self._collect_all_pages("followeds", uid)

        follow_map = {
            row["uid"]: row
            for row in (self._normalize_user_row(item) for item in follows)
            if row["uid"]
        }
        followed_map = {
            row["uid"]: row
            for row in (self._normalize_user_row(item) for item in followeds)
            if row["uid"]
        }
        mutual_uids = sorted(set(follow_map) & set(followed_map))
        friends = [follow_map.get(friend_uid) or followed_map[friend_uid] for friend_uid in mutual_uids]
        self.repository.upsert_friends(friends)
        return {
            "account_uid": uid,
            "friend_count": len(friends),
            "mutual_friends": friends,
            "friends": friends,
        }

    def list_friends(self) -> List[Dict[str, Any]]:
        return self.repository.list_friends()

    def list_recent_friends(self) -> List[Dict[str, Any]]:
        current_friend_uids = {str(item.get("uid") or "").strip() for item in self.repository.list_friends()}
        return [
            item
            for item in self.repository.list_recent_friends()
            if str(item.get("uid") or "").strip() in current_friend_uids
        ]

    def remember_friend(self, uid: str) -> List[Dict[str, Any]]:
        friend = self.repository.get_friend(uid)
        if not friend:
            raise RuntimeError("好友不存在，无法加入最近列表。")
        return self.repository.touch_recent_friend(
            uid=uid,
            friend_name=str(friend.get("nickname") or uid),
            avatar_url=str(friend.get("avatar_url") or ""),
        )

    def pin_recent_friend(self, uid: str) -> List[Dict[str, Any]]:
        friend = self.repository.get_friend(uid)
        if friend:
            self.remember_friend(uid)
        return self.repository.pin_recent_friend(uid)

    def unpin_recent_friend(self, uid: str) -> List[Dict[str, Any]]:
        return self.repository.unpin_recent_friend(uid)

    def delete_recent_friend(self, uid: str) -> List[Dict[str, Any]]:
        return self.repository.delete_recent_friend(uid)

    def clear_recent_friends(self) -> List[Dict[str, Any]]:
        return self.repository.clear_recent_friends()
