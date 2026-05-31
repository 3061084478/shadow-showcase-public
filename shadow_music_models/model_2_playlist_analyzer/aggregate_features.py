from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List


def _normalize_distribution(counter: Counter[str]) -> Dict[str, float]:
    total = sum(counter.values())
    if total <= 0:
        return {}
    return {key: round(value / total, 4) for key, value in counter.most_common()}


def _extract_year(date_text: str) -> int | None:
    text = str(date_text or "").strip()
    if len(text) < 4 or not text[:4].isdigit():
        return None
    return int(text[:4])


def _bucket_year(date_text: str) -> str:
    year = _extract_year(date_text)
    if year is None:
        return "未知"
    if year < 1990:
        return "1980s及更早"
    if year < 2000:
        return "1990s"
    if year < 2010:
        return "2000s"
    if year < 2020:
        return "2010s"
    return "2020s"


def _top_tag(tag_rows: Iterable[Dict[str, Any]]) -> str:
    for tag_row in tag_rows:
        tag = str(tag_row.get("tag") or "").strip()
        if tag and tag != "未知":
            return tag
    return "未知"


def _resolve_song_genre(song: Dict[str, Any]) -> str:
    direct_label = str(song.get("genre_label") or "").strip()
    if direct_label and direct_label != "未知":
        return direct_label
    return _top_tag(song.get("genre_tags") or [])


def _build_song_portrait(song: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(name).strip() for name in (song.get("artist_names") or []) if str(name).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
        "album_publish_time": str(song.get("album_publish_time") or "").strip(),
        "genre_label": str(song.get("genre_label") or _resolve_song_genre(song) or "未知").strip() or "未知",
    }


def _pick_representative_songs(songs: List[Dict[str, Any]], top_genre: str) -> List[Dict[str, Any]]:
    scored = []
    for song in songs:
        genre = _resolve_song_genre(song)
        score = 0
        if genre == top_genre and genre != "未知":
            score += 3
        score += 1 if not song.get("data_quality_flags") else 0
        score += 1 if str(song.get("album_publish_time") or "").strip() else 0
        scored.append((score, song))

    scored.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("song_name") or ""),
        )
    )

    representatives = []
    for _score, song in scored[:3]:
        genre = _resolve_song_genre(song)
        reasons = []
        if genre != "未知":
            reasons.append(f"命中主流派“{genre}”")
        if not reasons:
            reasons.append("结构化信息相对完整")
        representatives.append(
            {
                "song_name": str(song.get("song_name") or "").strip(),
                "artist_names": song.get("artist_names") or [],
                "album_name": str(song.get("album_name") or "").strip(),
                "album_publish_time": str(song.get("album_publish_time") or "").strip(),
                "genre_label": genre,
                "reason": "，".join(reasons),
            }
        )
    return representatives


def build_playlist_profile(
    playlist_id: str,
    playlist_name: str,
    songs: List[Dict[str, Any]],
    playlist_description: str = "",
) -> Dict[str, Any]:
    genre_counter: Counter[str] = Counter()
    era_counter: Counter[str] = Counter()
    artist_counter: Counter[str] = Counter()

    for song in songs:
        genre_counter.update([_resolve_song_genre(song)])
        era_counter.update([_bucket_year(str(song.get("album_publish_time") or ""))])
        artist_counter.update(str(name).strip() for name in (song.get("artist_names") or []) if str(name).strip())

    genre_distribution = _normalize_distribution(genre_counter)
    era_distribution = _normalize_distribution(era_counter)
    top_genre = next(iter(genre_distribution), "未知")

    representative_songs = _pick_representative_songs(songs, top_genre)
    song_portraits = [_build_song_portrait(song) for song in songs]

    return {
        "playlist_id": str(playlist_id or "").strip(),
        "playlist_name": str(playlist_name or "").strip(),
        "playlist_description": str(playlist_description or "").strip(),
        "song_count": len(songs),
        "songs": song_portraits,
        "genre_distribution": genre_distribution,
        "era_distribution": era_distribution,
        "top_artists": [
            {"artist_name": artist_name, "count": count}
            for artist_name, count in artist_counter.most_common(5)
        ],
        "representative_songs": representative_songs,
    }
