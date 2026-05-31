from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .config_store import ConfigStore
from .storage import SiteRepository


class AdminUnknownService:
    def __init__(self, config_store: ConfigStore, repository: SiteRepository) -> None:
        self.config_store = config_store
        self.repository = repository

    def list_unknown(self) -> List[Dict[str, Any]]:
        rows = self.repository.list_unknown_rows()
        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            key = "||".join(
                [
                    str(row.get("source_friend_uid") or "").strip(),
                    str(row.get("song_name") or "").strip().lower(),
                    "|".join(str(item).strip().lower() for item in (row.get("artist_names") or [])),
                    str(row.get("album_name") or "").strip().lower(),
                ]
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "song_name": row.get("song_name") or "",
                    "artist_names": row.get("artist_names") or [],
                    "album_name": row.get("album_name") or "",
                    "source_friend_uid": row.get("source_friend_uid") or "",
                }
            )
        return deduped

    def rebuild_unknown_file(self) -> Dict[str, Any]:
        rows = self.list_unknown()
        output_path = Path(self.config_store.output_dir) / "global_unknown_queue.json"
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"count": len(rows), "output_path": str(output_path), "rows": rows}
