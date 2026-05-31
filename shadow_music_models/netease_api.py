from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

import requests


class NeteaseApiError(Exception):
    pass


class NeteaseApiClient:
    def __init__(self, config: Dict[str, Any]):
        self.api_base = str(config["api_base"]).rstrip("/")
        self.cookie = str(config.get("cookie") or "")
        self.request_timeout = int(config.get("request_timeout", 10))
        self.session = requests.Session()
        self.session.trust_env = False

    def update_cookie(self, cookie: str) -> None:
        self.cookie = str(cookie or "")

    def clone(self) -> "NeteaseApiClient":
        return NeteaseApiClient(
            {
                "api_base": self.api_base,
                "cookie": self.cookie,
                "request_timeout": self.request_timeout,
            }
        )

    def _get(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        use_cookie: bool = True,
        cookie_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        final_params = dict(params)
        cookie = str(cookie_override if cookie_override is not None else self.cookie).strip()
        if use_cookie and cookie:
            final_params["cookie"] = cookie
        final_params["timestamp"] = time.time()
        try:
            response = self.session.get(
                f"{self.api_base}{path}",
                params=final_params,
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise NeteaseApiError(f"请求失败: {exc}") from exc
        except ValueError as exc:
            raise NeteaseApiError("接口返回不是合法 JSON") from exc

    @staticmethod
    def extract_status_code(data: Dict[str, Any]) -> int:
        return int(
            data.get("code")
            or data.get("body", {}).get("code")
            or data.get("data", {}).get("code")
            or -1
        )

    def get_login_status(self, cookie_override: Optional[str] = None) -> Dict[str, Any]:
        return self._get("/login/status", {}, cookie_override=cookie_override)

    def get_playlist_detail(self, playlist_id: str) -> Dict[str, Any]:
        data = self._get("/playlist/detail", {"id": playlist_id})
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取歌单详情失败: playlist_id={playlist_id}, response={data}")
        return data

    def get_playlist_tracks(
        self,
        playlist_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"id": playlist_id}
        if limit is not None:
            params["limit"] = int(limit)
        if offset is not None:
            params["offset"] = int(offset)
        data = self._get("/playlist/track/all", params)
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取歌单内容失败: playlist_id={playlist_id}, response={data}")
        return data

    def get_user_playlists(self, user_id: str, limit: int = 1000, offset: int = 0) -> Dict[str, Any]:
        data = self._get("/user/playlist", {"uid": user_id, "limit": limit, "offset": offset})
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取账号歌单失败: user_id={user_id}, response={data}")
        return data

    def get_song_detail(self, song_ids: Iterable[str]) -> Dict[str, Any]:
        ids = [str(song_id).strip() for song_id in song_ids if str(song_id).strip()]
        if not ids:
            return {"songs": [], "code": 200}
        data = self._get("/song/detail", {"ids": ",".join(ids)})
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取歌曲详情失败: ids={ids}, response={data}")
        return data

    def get_song_comments(self, song_id: str, limit: int = 10) -> Dict[str, Any]:
        data = self._get("/comment/music", {"id": song_id, "limit": limit})
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取歌曲评论失败: song_id={song_id}, response={data}")
        return data

    def get_song_lyric(self, song_id: str) -> Dict[str, Any]:
        data = self._get("/lyric", {"id": song_id})
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取歌词失败: song_id={song_id}, response={data}")
        return data

    def get_album_detail(self, album_id: str) -> Dict[str, Any]:
        data = self._get("/album", {"id": album_id})
        if self.extract_status_code(data) != 200:
            raise NeteaseApiError(f"获取专辑详情失败: album_id={album_id}, response={data}")
        return data

    def get_qr_key(self) -> str:
        data = self._get("/login/qr/key", {}, use_cookie=False)
        qr_key = str(data.get("data", {}).get("unikey") or "").strip()
        if not qr_key:
            raise NeteaseApiError(f"获取二维码 key 失败: {data}")
        return qr_key

    def create_qr(self, key: str) -> str:
        data = self._get("/login/qr/create", {"key": key}, use_cookie=False)
        qr_url = str(data.get("data", {}).get("qrurl") or "").strip()
        if not qr_url:
            raise NeteaseApiError(f"创建二维码失败: {data}")
        return qr_url

    def check_qr_status(self, key: str) -> Dict[str, Any]:
        data = self._get("/login/qr/check", {"key": key}, use_cookie=False)
        return {
            "code": int(data.get("code") or 0),
            "cookie": str(data.get("cookie") or "").strip(),
            "message": str(data.get("message") or data.get("msg") or "").strip(),
            "raw": data,
        }
