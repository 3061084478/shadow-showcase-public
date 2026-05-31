from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.config_store import ConfigStore
from shadow_music_models.model_2_playlist_analyzer import PlaylistAnalyzer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只对模型一结果运行模型二 PlaylistAnalyzer。")
    parser.add_argument("playlist_ids", nargs="+", help="一个或多个已完成模型一的 playlist_id。")
    return parser


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_playlist_description(config_store: ConfigStore, playlist_id: str) -> str:
    detail_path = config_store.raw_data_dir / "playlists" / f"{playlist_id}_detail.json"
    if not detail_path.exists():
        return ""
    payload = _load_json(detail_path)
    playlist = payload.get("playlist") or {}
    return str(playlist.get("description") or "").strip()


def _normalize_tagged_songs(songs: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for song in songs:
        row = dict(song)
        if not row.get("album_publish_time") and row.get("publish_time"):
            row["album_publish_time"] = str(row.get("publish_time") or "").strip()
        if not row.get("genre_label") and row.get("genre_tags"):
            first_tag = (row.get("genre_tags") or [{}])[0]
            row["genre_label"] = str(first_tag.get("tag") or "").strip()
        if "data_quality_flags" not in row:
            row["data_quality_flags"] = []
        normalized.append(row)
    return normalized


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    analyzer = PlaylistAnalyzer()

    for playlist_id in [str(value).strip() for value in args.playlist_ids if str(value).strip()]:
        tagged_path = config_store.output_data_dir / f"playlist_{playlist_id}_tagged.json"
        if not tagged_path.exists():
            print(f"未找到模型一输出文件：{tagged_path}")
            return 1

        tagged_payload = _load_json(tagged_path)
        songs = _normalize_tagged_songs(tagged_payload.get("songs") or [])
        playlist_name = str(tagged_payload.get("playlist_name") or "").strip()
        playlist_description = _load_playlist_description(config_store, playlist_id)

        profile_payload = analyzer.build_profile(
            playlist_id,
            playlist_name,
            songs,
            playlist_description,
        )
        analysis_payload = analyzer.generate(profile_payload)

        profile_path = config_store.output_data_dir / f"playlist_{playlist_id}_profile.json"
        analysis_path = config_store.output_data_dir / f"playlist_{playlist_id}_analysis.json"
        _write_json(profile_path, profile_payload)
        _write_json(analysis_path, analysis_payload)
        print(f"模型二输出已写入：{analysis_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
