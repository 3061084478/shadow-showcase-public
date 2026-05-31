from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config_store import ConfigStore
from .mapping_delta import apply_mapping_delta, load_mapping_bundle, save_mapping_bundle


def _utc_now_text() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


class MappingSyncService:
    def __init__(self, config_store: ConfigStore):
        self.config_store = config_store
        self.status_path = self.config_store.output_dir / "mapping_sync_status.json"
        self.state_path = self.config_store.output_dir / "mapping_delta_state.json"

    def _default_status(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "checked_at": "",
            "updated": False,
            "message": "尚未检查远端 delta 更新。",
            "base_version": 0,
            "embedded_delta_version": 0,
            "applied_delta_version": 0,
            "latest_delta_version": 0,
            "download_url": "",
            "mapping_path": "",
            "local_mapping_sha256": "",
            "applied_delta_count": 0,
        }

    def _default_state(self) -> Dict[str, Any]:
        base_version = self._base_version()
        embedded_delta_version = self._embedded_delta_version()
        return {
            "base_version": base_version,
            "embedded_delta_version": embedded_delta_version,
            "applied_delta_version": embedded_delta_version,
            "last_updated_at": "",
            "mapping_sha256": "",
        }

    def load_status(self) -> Dict[str, Any]:
        if not self.status_path.exists():
            return self._default_status()
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_status()
        if not isinstance(payload, dict):
            return self._default_status()
        merged = self._default_status()
        merged.update(payload)
        return merged

    def _save_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._default_status()
        merged.update(payload)
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        merged = self._default_state()
        merged.update(payload)
        return merged

    def _save_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._default_state()
        merged.update(payload)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    def _config(self) -> Dict[str, Any]:
        return self.config_store.load()

    def _is_enabled(self) -> bool:
        return bool(self._config().get("mapping_auto_update_enabled", False))

    def _timeout(self) -> int:
        raw = self._config().get("mapping_request_timeout_seconds")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 15
        return max(3, min(value, 120))

    def _mapping_path(self) -> Path:
        config = self._config()
        return self.config_store.resolve_workspace_path(str(config.get("genre_mapping_path") or "").strip())

    def _base_version(self) -> int:
        raw = self._config().get("mapping_base_version", 1)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 1

    def _manifest_url(self) -> str:
        return str(self._config().get("mapping_manifest_url") or "").strip()

    def _deltas_url(self) -> str:
        return str(self._config().get("mapping_deltas_url") or "").strip()

    def _embedded_delta_version(self) -> int:
        raw = self._config().get("mapping_embedded_delta_version", 0)
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _sha256_bytes(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _sha256_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _fetch_json(self, url: str) -> Dict[str, Any]:
        request = urllib.request.Request(url=url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout()) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"获取 delta manifest 失败：HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"获取 delta manifest 失败：{exc}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("delta manifest 响应不是合法 JSON。") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("delta manifest 响应不是 JSON 对象。")
        return payload

    def _fetch_deltas(self, base_version: int, from_delta_version: int, limit: int = 20) -> Dict[str, Any]:
        deltas_url = self._deltas_url()
        if not deltas_url:
            raise RuntimeError("未配置 mapping_deltas_url。")
        query = urllib.parse.urlencode(
            {
                "base_version": str(base_version),
                "from_delta": str(from_delta_version),
                "limit": str(limit),
            }
        )
        separator = "&" if "?" in deltas_url else "?"
        return self._fetch_json(f"{deltas_url}{separator}{query}")

    def _initialize_state_if_missing(self, mapping_path: Path) -> Dict[str, Any]:
        state = self._load_state()
        changed = False
        base_version = self._base_version()
        embedded_delta_version = self._embedded_delta_version()
        if int(state.get("base_version") or 0) != base_version:
            state["base_version"] = base_version
            changed = True
        if int(state.get("embedded_delta_version") or -1) != embedded_delta_version:
            state["embedded_delta_version"] = embedded_delta_version
            changed = True
        if not state.get("applied_delta_version"):
            state["applied_delta_version"] = embedded_delta_version
            changed = True
        local_sha = self._sha256_file(mapping_path)
        if local_sha and not state.get("mapping_sha256"):
            state["mapping_sha256"] = local_sha
            changed = True
        if changed:
            return self._save_state(state)
        return state

    def sync_latest_mapping_if_enabled(self, force: bool = False) -> Dict[str, Any]:
        mapping_path = self._mapping_path()
        local_sha = self._sha256_file(mapping_path)
        state = self._initialize_state_if_missing(mapping_path)
        base_version = int(state.get("base_version") or self._base_version())
        embedded_delta_version = int(state.get("embedded_delta_version") or self._embedded_delta_version())
        applied_delta_version = int(state.get("applied_delta_version") or embedded_delta_version)

        if not self._is_enabled():
            return self._save_status(
                {
                    "enabled": False,
                    "checked_at": _utc_now_text(),
                    "updated": False,
                    "message": "已关闭自动更新 mapping delta。",
                    "base_version": base_version,
                    "embedded_delta_version": embedded_delta_version,
                    "applied_delta_version": applied_delta_version,
                    "mapping_path": str(mapping_path),
                    "local_mapping_sha256": local_sha,
                }
            )

        manifest_url = self._manifest_url()
        if not manifest_url:
            return self._save_status(
                {
                    "enabled": True,
                    "checked_at": _utc_now_text(),
                    "updated": False,
                    "message": "未配置 mapping_manifest_url，已跳过远端检查。",
                    "base_version": base_version,
                    "embedded_delta_version": embedded_delta_version,
                    "applied_delta_version": applied_delta_version,
                    "mapping_path": str(mapping_path),
                    "local_mapping_sha256": local_sha,
                }
            )

        try:
            manifest = self._fetch_json(f"{manifest_url}?base_version={base_version}")
            latest_delta_version = int(manifest.get("latest_delta_version") or embedded_delta_version)
            if not force and latest_delta_version <= applied_delta_version:
                return self._save_status(
                    {
                        "enabled": True,
                        "checked_at": _utc_now_text(),
                        "updated": False,
                        "message": "本地 mapping delta 已是最新版，无需更新。",
                        "base_version": base_version,
                        "embedded_delta_version": embedded_delta_version,
                        "applied_delta_version": applied_delta_version,
                        "latest_delta_version": latest_delta_version,
                        "mapping_path": str(mapping_path),
                        "local_mapping_sha256": local_sha,
                    }
                )

            bundle = load_mapping_bundle(mapping_path)
            total_applied = 0
            current_delta_version = applied_delta_version
            latest_batch_url = ""

            while current_delta_version < latest_delta_version:
                response = self._fetch_deltas(base_version=base_version, from_delta_version=current_delta_version, limit=20)
                items = response.get("items") or []
                if not isinstance(items, list) or not items:
                    raise RuntimeError("远端未返回可应用的 delta。")
                latest_batch_url = str(response.get("request_url") or "")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    delta_version = int(item.get("delta_version") or 0)
                    previous_delta_version = int(item.get("previous_delta_version") or 0)
                    if previous_delta_version != current_delta_version:
                        raise RuntimeError(
                            f"delta 版本链不连续：当前 {current_delta_version}，收到 {previous_delta_version} -> {delta_version}"
                        )
                    bundle = apply_mapping_delta(bundle, item)
                    current_delta_version = delta_version
                    total_applied += 1
                if not bool(response.get("has_more")):
                    break

            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(mapping_path.parent), suffix=".tmp", encoding="utf-8") as temp_file:
                json.dump(bundle, temp_file, ensure_ascii=False, indent=2)
                temp_name = temp_file.name
            Path(temp_name).replace(mapping_path)

            final_sha = self._sha256_file(mapping_path)
            self._save_state(
                {
                    "base_version": base_version,
                    "embedded_delta_version": embedded_delta_version,
                    "applied_delta_version": current_delta_version,
                    "last_updated_at": _utc_now_text(),
                    "mapping_sha256": final_sha,
                }
            )
            return self._save_status(
                {
                    "enabled": True,
                    "checked_at": _utc_now_text(),
                    "updated": total_applied > 0,
                    "message": "已同步最新 mapping delta 到本地。" if total_applied > 0 else "未检测到新的 mapping delta。",
                    "base_version": base_version,
                    "embedded_delta_version": embedded_delta_version,
                    "applied_delta_version": current_delta_version,
                    "latest_delta_version": latest_delta_version,
                    "mapping_path": str(mapping_path),
                    "download_url": latest_batch_url,
                    "local_mapping_sha256": final_sha,
                    "applied_delta_count": total_applied,
                }
            )
        except Exception as exc:
            return self._save_status(
                {
                    "enabled": True,
                    "checked_at": _utc_now_text(),
                    "updated": False,
                    "message": f"自动检查 mapping delta 失败：{exc}",
                    "base_version": base_version,
                    "embedded_delta_version": embedded_delta_version,
                    "applied_delta_version": applied_delta_version,
                    "mapping_path": str(mapping_path),
                    "local_mapping_sha256": local_sha,
                }
            )

    def force_sync(self) -> Dict[str, Any]:
        return self.sync_latest_mapping_if_enabled(force=True)
