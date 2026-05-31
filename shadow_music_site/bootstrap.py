from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from .config_store import ConfigStore
from .netease_api import NeteaseApiClient, NeteaseApiError


DEFAULT_API_START_COMMAND = ["cmd", "/c", "npx", "NeteaseCloudMusicApi"]
DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"
NCM_API_PACKAGE = "NeteaseCloudMusicApi"
ANONYMOUS_TOKEN_FILENAME = "anonymous_token"
API_READY_TIMEOUT_SECONDS = 30
API_READY_POLL_INTERVAL_SECONDS = 0.5


class StartupBootstrapError(Exception):
    pass


class StartupBootstrap:
    def __init__(self, config_store: ConfigStore):
        self.config_store = config_store
        self.config = self.config_store.load()
        self.api_client = NeteaseApiClient(self.config)
        self.api_process: Optional[subprocess.Popen] = None

    def reload(self) -> Dict[str, Any]:
        self.config = self.config_store.load()
        self.api_client = NeteaseApiClient(self.config)
        return self.config

    def _extract_account_profile(self, data: Dict[str, Any]) -> Dict[str, str]:
        account = data.get("data", {}).get("account") or {}
        profile = data.get("data", {}).get("profile") or {}
        return {
            "user_id": str(account.get("id") or profile.get("userId") or "").strip(),
            "nickname": str(profile.get("nickname") or "").strip(),
            "avatar_url": str(profile.get("avatarUrl") or profile.get("avatar") or "").strip(),
        }

    def _resolve_api_host_port(self) -> tuple[str, int]:
        api_base = str(self.config.get("api_base") or "http://localhost:3000")
        parsed = urlparse(api_base)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3000
        return host, port

    def _resolve_api_start_command(self) -> list[str] | str:
        configured = self.config.get("api_start_command")
        if isinstance(configured, list) and configured:
            return [str(item) for item in configured]
        if isinstance(configured, str) and configured.strip():
            return configured
        bundled = self._resolve_bundled_api_start_command()
        if bundled:
            return bundled
        return DEFAULT_API_START_COMMAND

    def _resolve_bundled_api_start_command(self) -> Optional[list[str]]:
        _, target_port = self._resolve_api_host_port()
        runtime_dirs = [
            self.config_store.workspace_root / "V5" / "runtime" / NCM_API_PACKAGE,
            self.config_store.workspace_root / "runtime" / NCM_API_PACKAGE,
        ]
        for runtime_dir in runtime_dirs:
            server_path = runtime_dir / "server.js"
            node_bin = runtime_dir / "node.exe"
            if server_path.exists() and node_bin.exists():
                js_code = f"require({str(server_path)!r}).serveNcmApi({{checkVersion:false, port:{target_port}}})"
                return [str(node_bin), "-e", js_code]
            bat_path = runtime_dir / "start_api.bat"
            if bat_path.exists():
                return ["cmd", "/c", str(bat_path)]
        return None

    def _build_api_start_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
            "npm_config_proxy",
            "npm_config_https_proxy",
        ):
            env.pop(key, None)
        anonymous_token_path = self.config_store.tmp_dir / ANONYMOUS_TOKEN_FILENAME
        if not anonymous_token_path.exists():
            anonymous_token_path.write_text("anonymous", encoding="utf-8")
        env["npm_config_offline"] = "false"
        env["npm_config_cache"] = str(self.config_store.npm_cache_dir)
        env["TEMP"] = str(self.config_store.tmp_dir)
        env["TMP"] = str(self.config_store.tmp_dir)
        env["TMPDIR"] = str(self.config_store.tmp_dir)
        env["NO_PROXY"] = DEFAULT_NO_PROXY
        env["no_proxy"] = DEFAULT_NO_PROXY
        return env

    def _ensure_default_api_package_cached(self, env: Dict[str, str]) -> None:
        result = subprocess.run(
            ["cmd", "/c", "npx", "--yes", "--package", NCM_API_PACKAGE, "node", "-p", "2+2"],
            cwd=str(self.config_store.workspace_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return
        detail = (result.stderr or "").strip() or "未知错误"
        raise StartupBootstrapError(f"自动准备本地 API 运行包失败：{detail}")

    def _resolve_cached_server_path(self) -> str:
        matches = list(self.config_store.npm_cache_dir.glob(f"_npx/*/node_modules/{NCM_API_PACKAGE}/server.js"))
        if not matches:
            raise StartupBootstrapError("未找到本地缓存的 NeteaseCloudMusicApi server.js")
        return str(max(matches, key=lambda item: item.stat().st_mtime))

    def is_api_port_open(self) -> bool:
        host, port = self._resolve_api_host_port()
        try:
            with socket.create_connection((host, port), timeout=0.35):
                return True
        except OSError:
            return False

    def is_api_http_responding(self) -> bool:
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get(
                f"{self.api_client.api_base}/login/status",
                params={"timestamp": time.time()},
                timeout=(0.5, 1.0),
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return False
        return self.api_client.extract_status_code(data) == 200

    def start_api_service(self) -> None:
        command = self._resolve_api_start_command()
        env = self._build_api_start_env()
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        if command == DEFAULT_API_START_COMMAND:
            if shutil.which("node") is None:
                raise StartupBootstrapError("未检测到 node，请先安装 Node.js 后再启动。")
            self._ensure_default_api_package_cached(env)
            server_path = self._resolve_cached_server_path()
            _, target_port = self._resolve_api_host_port()
            js_code = f"require({server_path!r}).serveNcmApi({{checkVersion:false, port:{target_port}}})"
            command = ["node", "-e", js_code]

        self.api_process = subprocess.Popen(
            command,
            cwd=str(self.config_store.workspace_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            shell=isinstance(command, str),
        )

    def ensure_api_ready(self) -> None:
        if self.is_api_http_responding():
            return
        if self.is_api_port_open():
            raise StartupBootstrapError("检测到 API 端口已被占用，但当前服务不是兼容的 NeteaseCloudMusicApi。")
        self.start_api_service()
        deadline = time.time() + API_READY_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self.is_api_http_responding():
                return
            time.sleep(API_READY_POLL_INTERVAL_SECONDS)
        if self.is_api_port_open():
            raise StartupBootstrapError("本地 API 端口已打开，但接口未就绪。请检查端口冲突或 API 版本兼容性。")
        raise StartupBootstrapError("本地 API 服务启动超时，请检查 NeteaseCloudMusicApi 是否已正确安装。")

    def is_cookie_valid(self) -> bool:
        self.reload()
        cookie = str(self.config.get("cookie") or "").strip()
        if not cookie:
            return False
        try:
            data = self.api_client.get_login_status(cookie_override=cookie)
        except NeteaseApiError:
            return False
        if self.api_client.extract_status_code(data) != 200:
            return False
        account = data.get("data", {}).get("account") or {}
        profile = data.get("data", {}).get("profile") or {}
        if not profile:
            return False
        if account.get("anonimousUser"):
            return False
        return bool(account.get("id") or profile.get("userId"))

    def clear_saved_cookie(self) -> None:
        self.config_store.update(cookie="")
        self.reload()

    def create_qr_session(self) -> Dict[str, str]:
        self.ensure_api_ready()
        qr_key = self.api_client.get_qr_key()
        qr_payload = self.api_client.create_qr(qr_key)
        return {
            "key": qr_key,
            "qr_url": str(qr_payload.get("qr_url") or "").strip(),
            "qr_image": str(qr_payload.get("qr_image") or "").strip(),
        }

    def check_qr_session(self, key: str) -> Dict[str, Any]:
        payload = self.api_client.check_qr_status(key)
        if int(payload.get("code") or 0) == 803:
            cookie = str(payload.get("cookie") or "").strip()
            if cookie:
                self.config_store.update(cookie=cookie)
                self.reload()
        return payload

    def ensure_authenticated(self, force_relogin: bool = False) -> Dict[str, str]:
        self.ensure_api_ready()
        if force_relogin:
            self.clear_saved_cookie()
        if self.is_cookie_valid():
            return self._extract_account_profile(self.api_client.get_login_status())
        raise StartupBootstrapError("当前未登录，请先走二维码登录。")
