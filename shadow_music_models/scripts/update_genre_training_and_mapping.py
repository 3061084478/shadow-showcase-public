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
from shadow_music_models.model_1_song_tagger.genre_classifier import GenreClassifier
from shadow_music_models.model_1_song_tagger.song_tagger import GENRE_TAGS
from shadow_music_models.model_1_song_tagger.training_data import DatasetSpec, merge_training_datasets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="路线B后半段一键入口：并入 GPT 补标训练集，并立即重建流派映射集。"
    )
    parser.add_argument("extra_paths", nargs="+", help="GPT 补标 JSON 路径，可一次传多个。")
    parser.add_argument(
        "--merged",
        default="shadow_music_models/data/processed/song_genre_train_merged_singlelabel.json",
        help="当前总训练集路径。",
    )
    parser.add_argument(
        "--output",
        default="shadow_music_models/data/processed/song_genre_train_merged_singlelabel.json",
        help="合并后的总训练集输出路径。",
    )
    parser.add_argument(
        "--report",
        default="shadow_music_models/data/processed/song_genre_train_merged_singlelabel_report.json",
        help="合并报告输出路径。",
    )
    parser.add_argument(
        "--mapping-output",
        default="shadow_music_models/model_1_song_tagger/artifacts/genre_mapping.json",
        help="重建后的映射文件输出路径。",
    )
    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _expand_input_paths(raw_paths: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = Path(raw_path).expanduser()
        if path.is_dir():
            candidates = sorted(
                item
                for item in path.glob("*.json")
                if item.is_file() and not item.name.startswith("~$")
            )
        else:
            candidates = [path]
        for candidate in candidates:
            if candidate.name.startswith("~$"):
                continue
            normalized = str(candidate.resolve())
            if normalized in seen:
                continue
            seen.add(normalized)
            expanded.append(normalized)
    return expanded


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()

    merged_path = config_store.resolve_workspace_path(args.merged)
    if not merged_path.exists():
        print(f"未找到当前总训练集：{merged_path}")
        return 1

    expanded_paths = _expand_input_paths(args.extra_paths)
    if not expanded_paths:
        print("没有找到可并入的补充训练集 JSON。")
        return 1

    specs = [
        DatasetSpec(
            name=f"extra_{index}",
            path=config_store.resolve_workspace_path(path),
            priority=index,
        )
        for index, path in enumerate(expanded_paths, start=1)
    ]
    specs.append(
        DatasetSpec(
            name="current_merged",
            path=merged_path,
            priority=len(specs) + 1,
        )
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

    mapping_output_path = config_store.resolve_workspace_path(args.mapping_output)
    try:
        saved_mapping_path = GenreClassifier.train_and_save(
            merged["rows"],
            mapping_output_path,
            GENRE_TAGS,
        )
    except Exception as exc:
        print(f"重建映射集失败：{exc}")
        return 1

    print(f"融合训练集已写入：{output_path}")
    print(f"融合报告已写入：{report_path}")
    print(f"最终样本数：{merged['report']['total_rows']}")
    print(f"重复样本数：{merged['report']['duplicate_count']}")
    print(f"标签冲突重复数：{merged['report']['conflict_count']}")
    print(f"流派映射集已重建：{saved_mapping_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
