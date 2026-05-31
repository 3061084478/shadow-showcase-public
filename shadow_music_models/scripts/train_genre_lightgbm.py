from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.config_store import ConfigStore
from shadow_music_models.model_1_song_tagger.genre_classifier import GenreClassifier
from shadow_music_models.model_1_song_tagger.song_tagger import GENRE_TAGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建歌手/专辑/歌名映射型流派分类器。")
    parser.add_argument("dataset_path", nargs="?", help="训练集文件路径，支持 .json / .jsonl / .csv。")
    parser.add_argument(
        "--output",
        default="shadow_music_models/model_1_song_tagger/artifacts/genre_mapping.json",
        help="映射文件输出路径。",
    )
    parser.add_argument(
        "--artist-prior-weight",
        type=float,
        default=0.32,
        help="保留兼容参数，当前不会影响映射结果。",
    )
    parser.add_argument("--show-labels", action="store_true", help="仅打印当前流派标签池。")
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


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _load_json(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    raise ValueError("JSON 训练集必须是对象数组。")


def _load_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".jsonl":
        return _load_jsonl(path)
    if suffix == ".csv":
        return _load_csv(path)
    raise ValueError("训练集仅支持 .json / .jsonl / .csv。")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.show_labels:
        print("\n".join(tag for tag in GENRE_TAGS if tag != "未知"))
        return 0

    if not args.dataset_path:
        print("请提供训练集路径，或使用 --show-labels 仅查看流派标签池。")
        return 1

    dataset_path = Path(args.dataset_path)
    if not dataset_path.exists():
        print(f"训练集不存在：{dataset_path}")
        return 1

    try:
        rows = _load_rows(dataset_path)
    except Exception as exc:
        print(f"读取训练集失败：{exc}")
        return 1

    config_store = ConfigStore()
    output_path = config_store.resolve_workspace_path(args.output)
    try:
        saved_path = GenreClassifier.train_and_save(
            rows,
            output_path,
            GENRE_TAGS,
            artist_prior_weight=args.artist_prior_weight,
        )
    except Exception as exc:
        print(f"训练失败：{exc}")
        return 1

    print(f"流派模型训练完成：{saved_path}")
    print("当前已改为映射型分类器，未使用 LightGBM。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
