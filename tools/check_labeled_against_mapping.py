from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shadow_music_site.config_store import ConfigStore
from shadow_music_site.song_tagger import SongTagger


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python .\\tools\\check_labeled_against_mapping.py <labeled_json_path>")
        return 1

    labeled_path = Path(sys.argv[1]).resolve()
    rows = json.loads(labeled_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print("标注文件必须是顶层 JSON 数组。")
        return 1

    tagger = SongTagger(ConfigStore())
    matched = 0
    mismatched = 0
    unknown = 0

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        predicted = tagger.predict(
            {
                "song_name": row.get("song_name"),
                "artist_names": row.get("artist_names") or [],
                "album_name": row.get("album_name"),
            }
        )
        expected = str(row.get("genre_label") or "").strip()
        actual = str(predicted.get("genre_label") or "").strip()
        status = str(predicted.get("genre_status") or "").strip()
        if status == "unknown":
            unknown += 1
        elif actual == expected:
            matched += 1
        else:
            mismatched += 1
        print(
            json.dumps(
                {
                    "index": index,
                    "song_name": row.get("song_name"),
                    "artist_names": row.get("artist_names"),
                    "expected_genre_label": expected,
                    "actual_genre_label": actual,
                    "genre_status": status,
                    "genre_backend": predicted.get("genre_backend"),
                    "genre_evidence": predicted.get("genre_evidence"),
                },
                ensure_ascii=False,
            )
        )

    print(
        json.dumps(
            {
                "total": len(rows),
                "matched": matched,
                "mismatched": mismatched,
                "unknown": unknown,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
