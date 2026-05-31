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
from shadow_music_models.model_1_song_tagger import SongTagger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只对已采集歌单运行模型一 SongTagger。")
    parser.add_argument("playlist_ids", nargs="+", help="一个或多个已采集的 playlist_id。")
    return parser


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_file_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _load_collection_report(config_store: ConfigStore, playlist_id: str) -> dict:
    report_path = config_store.output_data_dir / f"playlist_{playlist_id}_collection_report.json"
    if not report_path.exists():
        return {}
    return json.loads(report_path.read_text(encoding="utf-8"))


def _build_unknown_song_row(song: dict) -> dict:
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
    }


def _build_tagged_song_row(song: dict, prediction: dict) -> dict:
    top_tag = str((prediction.get("genre_tags") or [{}])[0].get("tag") or "未知").strip() or "未知"
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
        "publish_time": str(song.get("album_publish_time") or "").strip(),
        "genre_label": top_tag,
    }


def _build_ai_ready_payload(playlist_name: str, tagged_songs: list[dict]) -> dict:
    filtered_songs = [
        {
            "song_name": str(song.get("song_name") or "").strip(),
            "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
            "album_name": str(song.get("album_name") or "").strip(),
            "publish_time": str(song.get("publish_time") or "").strip(),
            "genre_label": str(song.get("genre_label") or "").strip(),
        }
        for song in tagged_songs
        if str(song.get("genre_label") or "").strip() and str(song.get("genre_label") or "").strip() != "未知"
    ]
    return {
        "playlist_name": str(playlist_name or "").strip(),
        "songs": filtered_songs,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    tagger = SongTagger(config_store=config_store)

    for playlist_id in [str(value).strip() for value in args.playlist_ids if str(value).strip()]:
        processed_path = config_store.processed_data_dir / f"playlist_{playlist_id}_songs.jsonl"
        if not processed_path.exists():
            print(f"未找到已采集歌单文件：{processed_path}")
            return 1

        songs = _load_jsonl(processed_path)
        report = _load_collection_report(config_store, playlist_id)
        tagged_songs = []
        unknown_songs = []
        for song in songs:
            prediction = tagger.predict(song)
            tagged = _build_tagged_song_row(song, prediction)
            tagged_songs.append(tagged)
            if str((prediction.get("genre_tags") or [{}])[0].get("tag") or "") == "未知":
                unknown_songs.append(_build_unknown_song_row(song))

        output_path = config_store.output_data_dir / f"playlist_{playlist_id}_tagged.json"
        unknown_path = config_store.output_data_dir / f"playlist_{playlist_id}_unknown_songs.json"
        ai_ready_path = config_store.output_data_dir / f"playlist_{playlist_id}_for_ai.json"
        if unknown_songs:
            _write_json(unknown_path, unknown_songs)
        else:
            _remove_file_if_exists(unknown_path)
        playlist_name = str(report.get("playlist_name") or "").strip()
        _write_json(
            output_path,
            {
                "playlist_name": playlist_name,
                "songs": tagged_songs,
            },
        )
        _write_json(
            ai_ready_path,
            _build_ai_ready_payload(playlist_name, tagged_songs),
        )
        print(f"模型一输出已写入：{output_path}")
        print(f"外部AI使用文件已写入：{ai_ready_path}")
        if unknown_songs:
            print(f"未知流派待补标已写入：{unknown_path}")
        else:
            print(f"歌单 {playlist_id} 没有未知流派歌曲，未生成 unknown 文件。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
