from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict


class ConfigStore:
    def __init__(self, workspace_root: str | None = None, config_path: str | None = None):
        package_root = Path(__file__).resolve().parent
        self.package_root = package_root
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else package_root.parent
        self.config_path = Path(config_path).resolve() if config_path else package_root / "config.json"
        self._initialize_config_if_missing()

    @staticmethod
    def _default_payload() -> Dict[str, Any]:
        return {
            "api_base": "http://localhost:3000",
            "cookie": "",
            "request_timeout": 10,
            "comment_limit": 10,
            "qr_poll_interval_seconds": 2,
            "api_start_command": "",
            "emotion_lexicon_path": "情感词汇本体.xlsx",
            "genre_mapping_path": "shadow_music_models/model_1_song_tagger/artifacts/genre_mapping.json",
        }

    def _initialize_config_if_missing(self) -> None:
        if self.config_path.exists():
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        template_path = self.package_root / "config.template.json"
        if template_path.exists():
            shutil.copyfile(template_path, self.config_path)
            return
        self.save(self._default_payload())

    def load(self) -> Dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        merged = self._default_payload()
        merged.update(payload)
        return merged

    def save(self, payload: Dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def update(self, **fields: Any) -> Dict[str, Any]:
        payload = self.load()
        payload.update(fields)
        self.save(payload)
        return payload

    def resolve_workspace_path(self, value: str | None) -> Path:
        path_text = str(value or "").strip()
        if not path_text:
            return self.workspace_root
        path = Path(path_text)
        if path.is_absolute():
            return path
        return self.workspace_root / path

    @property
    def data_root(self) -> Path:
        path = self.package_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def raw_data_dir(self) -> Path:
        path = self.data_root / "raw"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def processed_data_dir(self) -> Path:
        path = self.data_root / "processed"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def output_data_dir(self) -> Path:
        path = self.data_root / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def runtime_tmp_dir(self) -> Path:
        path = self.data_root / "tmp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def npm_cache_dir(self) -> Path:
        path = self.workspace_root / "data" / "npm_cache"
        path.mkdir(parents=True, exist_ok=True)
        return path
