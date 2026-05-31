from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.config_store import ConfigStore
from shadow_music_models.model_1_song_tagger.genre_classifier import GenreClassifier
from shadow_music_models.model_1_song_tagger.song_tagger import GENRE_TAGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="分析真实歌单中的疑似误判样本和高混淆流派对。")
    parser.add_argument("playlist_id", help="已采集歌单的 playlist_id。")
    parser.add_argument("--top-k", type=int, default=15, help="输出疑似误判样本数量。")
    parser.add_argument("--gap-threshold", type=float, default=0.18, help="判定高混淆的 top1/top2 分差阈值。")
    parser.add_argument("--low-confidence", type=float, default=0.72, help="判定低置信的 top1 置信度阈值。")
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    processed_path = config_store.processed_data_dir / f"playlist_{args.playlist_id}_songs.jsonl"
    if not processed_path.exists():
        print(f"未找到已采集歌单文件：{processed_path}")
        return 1

    songs = _load_jsonl(processed_path)
    classifier = GenreClassifier(
        GENRE_TAGS,
        config_store.resolve_workspace_path(config_store.load().get("genre_mapping_path")),
    )

    suspicious_rows: list[dict] = []
    confusion_counter: Counter[str] = Counter()

    for song in songs:
        prediction = classifier.predict(song)
        tags = prediction.get("genre_tags") or []
        top1 = tags[0] if tags else {"tag": "未知", "confidence": 0.0}
        top2 = tags[1] if len(tags) > 1 else {"tag": "", "confidence": 0.0}
        gap = round(float(top1.get("confidence") or 0.0) - float(top2.get("confidence") or 0.0), 4)
        evidence = prediction.get("genre_evidence") or {}
        mapping_source = str(evidence.get("mapping_source") or "").strip()
        matched_key = str(evidence.get("matched_key") or "").strip()
        suspicious = (
            float(top1.get("confidence") or 0.0) < args.low_confidence
            or gap <= args.gap_threshold
        )
        if top1.get("tag") and top2.get("tag"):
            pair = " vs ".join(sorted([str(top1["tag"]), str(top2["tag"])]))
            if gap <= args.gap_threshold:
                confusion_counter.update([pair])

        if not suspicious:
            continue
        suspicious_rows.append(
            {
                "song_id": song.get("song_id"),
                "song_name": song.get("song_name"),
                "artist_names": song.get("artist_names") or [],
                "album_name": song.get("album_name") or "",
                "album_publish_time": song.get("album_publish_time") or "",
                "predicted_top1": top1,
                "predicted_top2": top2,
                "confidence_gap": gap,
                "mapping_source": mapping_source,
                "matched_key": matched_key,
            }
        )

    suspicious_rows.sort(
        key=lambda item: (
            -(1 if item["predicted_top2"].get("tag") else 0),
            item["confidence_gap"],
            item["predicted_top1"].get("confidence") or 0.0,
            item["song_name"] or "",
        )
    )

    report = {
        "playlist_id": str(args.playlist_id),
        "processed_path": str(processed_path),
        "song_count": len(songs),
        "low_confidence_threshold": args.low_confidence,
        "gap_threshold": args.gap_threshold,
        "suspicious_sample_count": len(suspicious_rows),
        "top_confusion_pairs": [
            {"pair": pair, "count": count}
            for pair, count in confusion_counter.most_common(10)
        ],
        "suspicious_samples": suspicious_rows[: args.top_k],
    }
    output_path = config_store.output_data_dir / f"playlist_{args.playlist_id}_genre_confusion_report.json"
    _write_json(output_path, report)

    print(f"歌单流派混淆分析已写入：{output_path}")
    print(f"疑似误判样本：{len(suspicious_rows)}")
    if report["top_confusion_pairs"]:
        print("最容易混淆的流派对：")
        for item in report["top_confusion_pairs"][:5]:
            print(f"- {item['pair']} ({item['count']})")
    else:
        print("当前歌单没有命中高混淆流派对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
