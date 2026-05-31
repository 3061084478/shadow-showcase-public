from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.collectors import PlaylistCollector
from shadow_music_models.config_store import ConfigStore
from shadow_music_models.model_1_song_tagger import SongTagger
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按歌单列表完成采集和模型一打标，并汇总全部 unknown 歌曲供 ChatGPT 批量标注。"
    )
    parser.add_argument("playlist_ids", nargs="+", help="一个或多个歌单 ID，或一个形如 ['a','b'] 的列表字符串。")
    parser.add_argument(
        "--output",
        default="shadow_music_models/data/outputs/playlist_unknowns_for_chatgpt.json",
        help="汇总 unknown 歌曲 JSON 输出路径。默认只输出歌曲数组，适合直接丢给 ChatGPT。",
    )
    parser.add_argument(
        "--report",
        default="shadow_music_models/data/outputs/playlist_unknowns_for_chatgpt_report.json",
        help="采集与 unknown 汇总报告输出路径。",
    )
    parser.add_argument("--force-relogin", action="store_true", help="采集前强制重新扫码登录。")
    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _flatten_playlist_id_inputs(raw_values: Sequence[str]) -> list[str]:
    text = " ".join(str(item).strip() for item in raw_values if str(item).strip())
    if not text:
        return []

    extracted: list[str] = []
    seen: set[str] = set()

    try:
        if text.startswith("[") and text.endswith("]"):
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                for item in parsed:
                    value = str(item).strip()
                    if value and value not in seen:
                        extracted.append(value)
                        seen.add(value)
                if extracted:
                    return extracted
    except Exception:
        pass

    for match in re.findall(r"\d{3,}", text):
        if match in seen:
            continue
        extracted.append(match)
        seen.add(match)
    return extracted


def _build_unknown_song_row(song: dict[str, Any]) -> dict[str, Any]:
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
    }


def _build_tagged_song_row(song: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    top_tag = str((prediction.get("genre_tags") or [{}])[0].get("tag") or "未知").strip() or "未知"
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
        "publish_time": str(song.get("album_publish_time") or "").strip(),
        "genre_label": top_tag,
    }


def _dedupe_unknown_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        song_name = str(row.get("song_name") or "").strip()
        album_name = str(row.get("album_name") or "").strip()
        artist_names = [str(item).strip() for item in (row.get("artist_names") or []) if str(item).strip()]
        if not song_name or not artist_names:
            continue
        key = "::".join(
            [
                song_name.lower(),
                album_name.lower(),
                "|".join(sorted(name.lower() for name in artist_names)),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "song_name": song_name,
                "artist_names": artist_names,
                "album_name": album_name,
            }
        )
    return deduped


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    playlist_ids = _flatten_playlist_id_inputs(args.playlist_ids)
    if not playlist_ids:
        print("没有可处理的 playlist_id。")
        return 1

    config_store = ConfigStore()
    bootstrap = StartupBootstrap(config_store)
    try:
        profile = bootstrap.ensure_authenticated(force_relogin=bool(args.force_relogin))
    except StartupBootstrapError as exc:
        print(f"采集前认证失败：{exc}")
        return 1

    collector = PlaylistCollector(bootstrap.api_client, config_store)
    tagger = SongTagger(config_store=config_store)
    aggregated_unknown_rows: list[dict[str, Any]] = []
    report_items: list[dict[str, Any]] = []

    print(f"API 已就绪，当前账号：{profile.get('nickname') or '未知用户'}")

    for playlist_id in playlist_ids:
        try:
            collected = collector.collect_playlist(playlist_id)
            tagged_rows: list[dict[str, Any]] = []
            unknown_rows: list[dict[str, Any]] = []
            for song in collected["songs"]:
                prediction = tagger.predict(song)
                tagged_rows.append(_build_tagged_song_row(song, prediction))
                top_tag = str((prediction.get("genre_tags") or [{}])[0].get("tag") or "").strip()
                if top_tag == "未知":
                    unknown_row = _build_unknown_song_row(song)
                    unknown_rows.append(unknown_row)
                    aggregated_unknown_rows.append(unknown_row)

            tagged_path = config_store.output_data_dir / f"playlist_{playlist_id}_tagged.json"
            unknown_path = config_store.output_data_dir / f"playlist_{playlist_id}_unknown_songs.json"
            _write_json(
                tagged_path,
                {
                    "playlist_name": str(collected.get("playlist_name") or "").strip(),
                    "songs": tagged_rows,
                },
            )
            _write_json(unknown_path, unknown_rows)

            report_items.append(
                {
                    "playlist_id": playlist_id,
                    "status": "ok",
                    "song_count": len(collected["songs"]),
                    "unknown_count": len(unknown_rows),
                    "tagged_path": str(tagged_path),
                    "unknown_path": str(unknown_path),
                }
            )
            print(f"{playlist_id} | songs {len(collected['songs'])} | unknown {len(unknown_rows)}")
        except Exception as exc:
            report_items.append(
                {
                    "playlist_id": playlist_id,
                    "status": "error",
                    "song_count": 0,
                    "unknown_count": 0,
                    "error": str(exc),
                }
            )
            print(f"{playlist_id} | error | {exc}")

    deduped_unknown_rows = _dedupe_unknown_rows(aggregated_unknown_rows)
    output_path = config_store.resolve_workspace_path(args.output)
    report_path = config_store.resolve_workspace_path(args.report)

    _write_json(output_path, deduped_unknown_rows)
    _write_json(
        report_path,
        {
            "playlist_ids": playlist_ids,
            "playlist_count": len(playlist_ids),
            "raw_unknown_count": len(aggregated_unknown_rows),
            "deduped_unknown_count": len(deduped_unknown_rows),
            "results": report_items,
            "output_path": str(output_path),
        },
    )

    print(f"汇总 unknown 已写入：{output_path}")
    print(f"汇总报告已写入：{report_path}")
    print(f"raw_unknown={len(aggregated_unknown_rows)}")
    print(f"deduped_unknown={len(deduped_unknown_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
