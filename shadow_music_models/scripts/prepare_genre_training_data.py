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
from shadow_music_models.model_1_song_tagger.training_data import DatasetSpec, merge_training_datasets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="整理并融合流派训练集，输出单标签去重后的总训练集。")
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="额外补充训练集路径，可重复传入；会按比基础集更高的优先级并入总训练集。",
    )
    parser.add_argument(
        "--base",
        default="song_genre_train_all_21genres_multilabel_exact_merged.json",
        help="原始基础训练集路径。",
    )
    parser.add_argument(
        "--top10",
        default="song_genre_train_extra_21genres_top10_singlelabel.json",
        help="Top10 歌手补充训练集路径。",
    )
    parser.add_argument(
        "--top11-50",
        dest="top11_50",
        default="song_genre_train_extra_top11_50_21genres_singlelabel.json",
        help="Top11-50 歌手补充训练集路径。",
    )
    parser.add_argument(
        "--output",
        default="shadow_music_models/data/processed/song_genre_train_merged_singlelabel.json",
        help="融合后的训练集输出路径。",
    )
    parser.add_argument(
        "--report",
        default="shadow_music_models/data/processed/song_genre_train_merged_singlelabel_report.json",
        help="融合统计报告输出路径。",
    )
    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    specs = []
    for index, extra_path in enumerate(args.extra, start=1):
        specs.append(
            DatasetSpec(
                name=f"extra_{index}",
                path=config_store.resolve_workspace_path(extra_path),
                priority=index,
            )
        )

    base_priority = len(specs) + 1
    specs.extend(
        [
        DatasetSpec(
            name="top10_singlelabel",
            path=config_store.resolve_workspace_path(args.top10),
            priority=base_priority,
        ),
        DatasetSpec(
            name="top11_50_singlelabel",
            path=config_store.resolve_workspace_path(args.top11_50),
            priority=base_priority + 1,
        ),
        DatasetSpec(
            name="base_singlelabel_firsttag",
            path=config_store.resolve_workspace_path(args.base),
            priority=base_priority + 2,
        ),
        ]
    )

    try:
        merged = merge_training_datasets(specs)
    except Exception as exc:
        print(f"整理训练集失败：{exc}")
        return 1

    output_path = config_store.resolve_workspace_path(args.output)
    report_path = config_store.resolve_workspace_path(args.report)
    _write_json(output_path, merged["rows"])
    _write_json(report_path, merged["report"])

    print(f"融合训练集已写入：{output_path}")
    print(f"融合报告已写入：{report_path}")
    print(f"最终样本数：{merged['report']['total_rows']}")
    print(f"重复样本数：{merged['report']['duplicate_count']}")
    print(f"标签冲突重复数：{merged['report']['conflict_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
