from __future__ import annotations

from typing import Any, Dict, Iterable, List


def build_playlist_summaries(playlists: Iterable[Dict[str, Any]], current_user_id: str = "") -> List[Dict[str, Any]]:
    normalized_user_id = str(current_user_id or "").strip()
    summaries: List[Dict[str, Any]] = []
    for item in playlists:
        creator = item.get("creator") or {}
        creator_id = str(creator.get("userId") or item.get("userId") or "").strip()
        summaries.append(
            {
                "playlist_id": str(item.get("id") or "").strip(),
                "playlist_name": str(item.get("name") or "").strip(),
                "track_count": int(item.get("trackCount") or 0),
                "creator_nickname": str(creator.get("nickname") or "").strip(),
                "creator_user_id": creator_id,
                "subscribed": bool(item.get("subscribed")),
                "is_mine": bool(normalized_user_id and creator_id and creator_id == normalized_user_id),
            }
        )
    return summaries


def parse_playlist_selection(selection_text: str, playlists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = str(selection_text or "").strip().lower()
    if not normalized:
        raise ValueError("未输入任何序号。")
    if not playlists:
        raise ValueError("当前没有可选歌单。")
    if normalized == "all":
        return playlists

    tokens = [token.strip() for token in normalized.replace("，", ",").split(",") if token.strip()]
    if not tokens:
        raise ValueError("未识别到有效序号。")

    selected: List[Dict[str, Any]] = []
    used_indexes: set[int] = set()
    for token in tokens:
        if not token.isdigit():
            raise ValueError(f"存在非法序号：{token}")
        index = int(token)
        if index < 1 or index > len(playlists):
            raise ValueError(f"序号超出范围：{index}")
        if index in used_indexes:
            continue
        selected.append(playlists[index - 1])
        used_indexes.add(index)
    return selected
