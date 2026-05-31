from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict

PORTABLE_APP_ROOT_ENV = "SHADOW_APP_ROOT"
PORTABLE_DATA_ROOT_ENV = "SHADOW_DATA_ROOT"
PORTABLE_CONFIG_PATH_ENV = "SHADOW_CONFIG_PATH"
DEFAULT_UNKNOWN_SONG_SUBMIT_URL = (
    "https://shadow-unknown-prod-d9bwced9ed8d-1438208321.ap-shanghai.app.tcloudbase.com"
    "/api/unknown-song/batch-submit"
)
DEFAULT_MAPPING_API_BASE_URL = "https://shadow-unknown-prod-d9bwced9ed8d-1438208321.ap-shanghai.app.tcloudbase.com"
DEFAULT_MAPPING_MANIFEST_URL = f"{DEFAULT_MAPPING_API_BASE_URL}/api/mapping/delta-manifest"
DEFAULT_MAPPING_DELTAS_URL = f"{DEFAULT_MAPPING_API_BASE_URL}/api/mapping/deltas"


class ConfigStore:
    def __init__(self, workspace_root: str | None = None, config_path: str | None = None):
        self.package_root = Path(__file__).resolve().parent
        env_workspace_root = os.environ.get(PORTABLE_APP_ROOT_ENV, "").strip()
        env_data_root = os.environ.get(PORTABLE_DATA_ROOT_ENV, "").strip()
        env_config_path = os.environ.get(PORTABLE_CONFIG_PATH_ENV, "").strip()

        self.workspace_root = (
            Path(workspace_root).resolve()
            if workspace_root
            else Path(env_workspace_root).resolve()
            if env_workspace_root
            else self.package_root.parent
        )
        self._portable_data_root = Path(env_data_root).resolve() if env_data_root else None
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else Path(env_config_path).resolve()
            if env_config_path
            else self.package_root / "config.json"
        )
        self._initialize_config_if_missing()

    @staticmethod
    def _default_payload() -> Dict[str, Any]:
        return {
            "api_base": "http://127.0.0.1:3000",
            "cookie": "",
            "request_timeout": 10,
            "qr_poll_interval_seconds": 2,
            "api_start_command": "",
            "default_limit": 50,
            "page_window_size": 30,
            "sleep_seconds": 0.25,
            "genre_mapping_path": "shadow_music_models/model_1_song_tagger/artifacts/genre_mapping.json",
            "mapping_auto_update_enabled": True,
            "mapping_base_version": 1,
            "mapping_embedded_delta_version": 1,
            "mapping_manifest_url": DEFAULT_MAPPING_MANIFEST_URL,
            "mapping_deltas_url": DEFAULT_MAPPING_DELTAS_URL,
            "mapping_request_timeout_seconds": 15,
            "friend_export_prompt_title": "闊充箰浜烘牸渚у啓鍗忚",
            "auto_archive_all_friends": True,
            "auto_archive_initialized": False,
            "auto_archive_last_run": "",
            "shadow_playlist_id": "",
            "shadow_playlist_name": "",
            "shadow_playlist_strategy": "use_existing",
            "shadow_playlist_private": False,
            "shadow_playlist_last_set_at": "",
            "allow_unknown_song_contribution": False,
            "unknown_song_submit_url": DEFAULT_UNKNOWN_SONG_SUBMIT_URL,
            "unknown_song_admin_token": "",
        }

    def _load_template_payload(self) -> Dict[str, Any]:
        template_path = self.package_root / "config.template.json"
        if not template_path.exists():
            return {}
        try:
            with template_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

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
        template_payload = self._load_template_payload()
        merged.update(template_payload)
        merged.update(payload)
        if not str(payload.get("unknown_song_submit_url", "")).strip():
            template_submit_url = str(template_payload.get("unknown_song_submit_url", "")).strip()
            if template_submit_url:
                merged["unknown_song_submit_url"] = template_submit_url
            else:
                merged["unknown_song_submit_url"] = DEFAULT_UNKNOWN_SONG_SUBMIT_URL
        if not str(payload.get("mapping_manifest_url", "")).strip():
            template_manifest_url = str(template_payload.get("mapping_manifest_url", "")).strip()
            merged["mapping_manifest_url"] = template_manifest_url or DEFAULT_MAPPING_MANIFEST_URL
        if not str(payload.get("mapping_deltas_url", "")).strip():
            template_deltas_url = str(template_payload.get("mapping_deltas_url", "")).strip()
            merged["mapping_deltas_url"] = template_deltas_url or DEFAULT_MAPPING_DELTAS_URL
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
        text = str(value or "").strip()
        if not text:
            return self.workspace_root
        path = Path(text)
        if path.is_absolute():
            return path
        return self.workspace_root / path

    @property
    def data_root(self) -> Path:
        path = self._portable_data_root or (self.package_root / "data")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def archive_dir(self) -> Path:
        path = self.data_root / "archive"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def output_dir(self) -> Path:
        path = self.data_root / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def tmp_dir(self) -> Path:
        path = self.data_root / "tmp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def npm_cache_dir(self) -> Path:
        path = self.data_root / "npm_cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> Path:
        path = self.archive_dir / "shadow_music_site.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
