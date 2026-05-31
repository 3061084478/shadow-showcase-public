from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
from typing import Any, Dict, Iterable, List

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.config_store import ConfigStore
from shadow_music_models.model_1_song_tagger.training_data import (
    build_artist_name_set,
    load_json_rows,
    normalize_artist_names,
)
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只输出歌单里不在总训练集里的歌手。")
    parser.add_argument("playlist_id", help="网易云歌单 playlist_id。")
    parser.add_argument(
        "--training-data",
        default="shadow_music_models/data/processed/song_genre_train_merged_singlelabel.json",
        help="用于比对歌手覆盖的训练集路径。",
    )
    parser.add_argument(
        "--force-relogin",
        action="store_true",
        help="请求前强制重新扫码登录。",
    )
    return parser


def build_missing_artist_names(
    songs: Iterable[Dict[str, Any]],
    training_rows: Iterable[Dict[str, Any]],
) -> List[str]:
    known_artist_names = build_artist_name_set(training_rows)
    missing_artist_names: Dict[str, str] = {}

    for song in songs:
        for artist_name in normalize_artist_names(song.get("artist_names") or []):
            artist_key = artist_name.lower()
            if artist_key in known_artist_names or artist_key in missing_artist_names:
                continue
            missing_artist_names[artist_key] = artist_name

    return sorted(missing_artist_names.values(), key=lambda item: item.lower())


def fetch_playlist_songs(playlist_id: str, *, force_relogin: bool) -> List[Dict[str, Any]]:
    config_store = ConfigStore()
    bootstrap = StartupBootstrap(config_store)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.ensure_authenticated(force_relogin=force_relogin)
    except StartupBootstrapError as exc:
        raise RuntimeError(f"采集前认证失败：{exc}") from exc

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            track_data = bootstrap.api_client.get_playlist_tracks(str(playlist_id))
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    songs: List[Dict[str, Any]] = []
    for track in track_data.get("songs") or []:
        songs.append(
            {
                "song_id": str(track.get("id") or "").strip(),
                "song_name": str(track.get("name") or "").strip(),
                "artist_names": [
                    str(artist.get("name") or "").strip()
                    for artist in (track.get("ar") or [])
                    if str(artist.get("name") or "").strip()
                ],
            }
        )
    return songs


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    training_data_path = config_store.resolve_workspace_path(args.training_data)
    if not training_data_path.exists():
        sys.stderr.write(f"未找到训练集文件：{training_data_path}\n")
        return 1

    training_rows = load_json_rows(training_data_path)
    try:
        songs = fetch_playlist_songs(str(args.playlist_id), force_relogin=bool(args.force_relogin))
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    for artist_name in build_missing_artist_names(songs, training_rows):
        print(artist_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
