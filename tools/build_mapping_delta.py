from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shadow_music_site.mapping_delta import compute_mapping_delta, load_mapping_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a mapping delta from previous and current full mapping bundles.")
    parser.add_argument("--previous", required=True, help="Path to the previously published full genre_mapping.json")
    parser.add_argument("--current", required=True, help="Path to the newly built full genre_mapping.json")
    parser.add_argument("--base-version", type=int, required=True, help="Base version embedded in the app")
    parser.add_argument("--delta-version", type=int, required=True, help="New delta version to publish")
    parser.add_argument(
        "--previous-delta-version",
        type=int,
        required=True,
        help="Previous published delta version for this base",
    )
    parser.add_argument("--output", required=True, help="Output path for the generated delta json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    previous_bundle = load_mapping_bundle(Path(args.previous))
    current_bundle = load_mapping_bundle(Path(args.current))
    delta_payload = compute_mapping_delta(
        previous_bundle,
        current_bundle,
        base_version=args.base_version,
        delta_version=args.delta_version,
        previous_delta_version=args.previous_delta_version,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(delta_payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
