from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shadow_music_site.mapping_delta import compute_mapping_delta, load_mapping_bundle

DEFAULT_MERGED = Path("shadow_music_models/data/processed/song_genre_train_merged_singlelabel.json")
DEFAULT_REPORT = Path("shadow_music_models/data/processed/song_genre_train_merged_singlelabel_report.json")
DEFAULT_MAPPING = Path("shadow_music_models/model_1_song_tagger/artifacts/genre_mapping.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare one mapping delta release from labeled json inputs."
    )
    parser.add_argument(
        "labeled_inputs",
        nargs="+",
        help="One or more labeled json files or directories to feed into update_genre_training_and_mapping.py",
    )
    parser.add_argument("--base-version", type=int, required=True, help="Current app base version")
    parser.add_argument("--delta-version", type=int, required=True, help="New delta version to publish")
    parser.add_argument(
        "--previous-delta-version",
        type=int,
        required=True,
        help="Previous published delta version on this base chain",
    )
    parser.add_argument(
        "--release-dir",
        default="build/mapping-release",
        help="Directory for this release output",
    )
    parser.add_argument(
        "--merged",
        default=str(DEFAULT_MERGED),
        help="Merged dataset path used by the existing build script",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT),
        help="Merged report path used by the existing build script",
    )
    parser.add_argument(
        "--mapping-output",
        default=str(DEFAULT_MAPPING),
        help="Full mapping output path used by the existing build script",
    )
    return parser.parse_args()


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def main() -> int:
    args = parse_args()
    release_root = (REPO_ROOT / args.release_dir).resolve()
    release_root.mkdir(parents=True, exist_ok=True)

    merged_path = (REPO_ROOT / args.merged).resolve()
    report_path = (REPO_ROOT / args.report).resolve()
    mapping_output_path = (REPO_ROOT / args.mapping_output).resolve()

    if not mapping_output_path.exists():
        print(f"未找到当前 full mapping：{mapping_output_path}")
        return 1

    previous_mapping_path = release_root / "previous_genre_mapping.json"
    current_mapping_path = release_root / "current_genre_mapping.json"
    delta_output_path = release_root / f"delta-{args.delta_version}.json"
    release_meta_path = release_root / "release-meta.json"

    _copy_file(mapping_output_path, previous_mapping_path)

    command = [
        sys.executable,
        str((REPO_ROOT / "shadow_music_models/scripts/update_genre_training_and_mapping.py").resolve()),
        *args.labeled_inputs,
        "--merged",
        str(merged_path),
        "--output",
        str(merged_path),
        "--report",
        str(report_path),
        "--mapping-output",
        str(mapping_output_path),
    ]

    run = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if run.returncode != 0:
        print(run.stdout)
        print(run.stderr)
        print(f"完整构建失败，返回码：{run.returncode}")
        return run.returncode

    _copy_file(mapping_output_path, current_mapping_path)
    if report_path.exists():
        _copy_file(report_path, release_root / report_path.name)
    if merged_path.exists():
        _copy_file(merged_path, release_root / merged_path.name)

    previous_bundle = load_mapping_bundle(previous_mapping_path)
    current_bundle = load_mapping_bundle(current_mapping_path)
    delta_payload = compute_mapping_delta(
        previous_bundle,
        current_bundle,
        base_version=args.base_version,
        delta_version=args.delta_version,
        previous_delta_version=args.previous_delta_version,
    )
    delta_output_path.write_text(json.dumps(delta_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    release_meta = {
        "base_version": args.base_version,
        "delta_version": args.delta_version,
        "previous_delta_version": args.previous_delta_version,
        "labeled_inputs": args.labeled_inputs,
        "previous_mapping": str(previous_mapping_path),
        "current_mapping": str(current_mapping_path),
        "delta_output": str(delta_output_path),
        "merged_output": str(merged_path),
        "report_output": str(report_path),
        "build_stdout": run.stdout,
        "build_stderr": run.stderr,
    }
    release_meta_path.write_text(json.dumps(release_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"本次 release 目录：{release_root}")
    print(f"delta 已生成：{delta_output_path}")
    print(f"旧 full mapping 备份：{previous_mapping_path}")
    print(f"新 full mapping 备份：{current_mapping_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
